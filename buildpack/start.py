#!/usr/bin/env python3
import atexit
import datetime
import json
import logging
import os
import signal
import subprocess
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from buildpack import (
    appdynamics,
    datadog,
    instadeploy,
    java,
    newrelic,
    nginx,
    runtime,
    telegraf,
    util,
)
from buildpack.runtime_components import security
from lib.m2ee import M2EE as m2ee_class

BUILDPACK_VERSION = "4.5.8"

m2ee = None
app_is_restarting = False
nginx_process = None


class Maintenance(BaseHTTPRequestHandler):
    MESSAGE = "App is in maintenance mode. To turn off unset DEBUG_CONTAINER variable"

    def _handle_all(self):
        logging.warning(self.MESSAGE)
        self.send_response(503)
        self.send_header("X-Mendix-Cloud-Mode", "maintenance")
        self.end_headers()
        self.wfile.write(self.MESSAGE.encode("utf-8"))

    def do_GET(self):
        self._handle_all()

    def do_POST(self):
        self._handle_all()

    def do_PUT(self):
        self._handle_all()

    def do_HEAD(self):
        self._handle_all()


if os.environ.get("DEBUG_CONTAINER", "false").lower() == "true":
    logging.warning(Maintenance.MESSAGE)
    port = int(os.environ.get("PORT", 8080))
    httpd = HTTPServer(("", port), Maintenance)
    httpd.serve_forever()


def pre_process_m2ee_yaml():
    subprocess.check_call(
        [
            "sed",
            "-i",
            "s|BUILD_PATH|%s|g; s|RUNTIME_PORT|%d|; s|ADMIN_PORT|%d|; s|PYTHONPID|%d|"
            % (
                os.getcwd(),
                util.get_runtime_port(),
                util.get_admin_port(),
                os.getpid(),
            ),
            ".local/m2ee.yaml",
        ]
    )


def set_up_m2ee_client(vcap_data):
    client = m2ee_class(
        yamlfiles=[".local/m2ee.yaml"],
        load_default_files=False,
        config={
            "m2ee": {
                # this is named admin_pass, but it's the verification http header
                # to communicate with the internal management port of the runtime
                "admin_pass": security.get_m2ee_password()
            }
        },
    )

    version = client.config.get_runtime_version()

    mendix_runtimes_path = "/usr/local/share/mendix-runtimes.git"
    mendix_runtime_version_path = os.path.join(
        os.getcwd(), "runtimes", str(version)
    )
    if os.path.isdir(mendix_runtimes_path) and not os.path.isdir(
        mendix_runtime_version_path
    ):
        util.mkdir_p(mendix_runtime_version_path)
        env = dict(os.environ)
        env["GIT_WORK_TREE"] = mendix_runtime_version_path

        # checkout the runtime version
        process = subprocess.Popen(
            ["git", "checkout", str(version), "-f"],
            cwd=mendix_runtimes_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        process.communicate()
        if process.returncode != 0:
            logging.info("Mendix %s is not available in the rootfs", version)
            logging.info(
                "Fallback (1): trying to fetch Mendix %s using git", version
            )
            process = subprocess.Popen(
                [
                    "git",
                    "fetch",
                    "origin",
                    "refs/tags/{0}:refs/tags/{0}".format(str(version)),
                    "&&",
                    "git",
                    "checkout",
                    str(version),
                    "-f",
                ],
                cwd=mendix_runtimes_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            process.communicate()
            if process.returncode != 0:
                logging.info(
                    "Unable to fetch Mendix {} using git".format(version)
                )
                url = util.get_blobstore_url(
                    "/runtime/mendix-%s.tar.gz" % str(version)
                )
                logging.info(
                    "Fallback (2): downloading Mendix {} from {}".format(
                        version, url
                    )
                )
                util.download_and_unpack(
                    url, os.path.join(os.getcwd(), "runtimes")
                )

        client.reload_config()
    runtime.set_runtime_config(
        client.config._model_metadata,
        client.config._conf["mxruntime"],
        vcap_data,
        client,
    )
    java_version = runtime.get_java_version(
        client.config.get_runtime_version()
    )["version"]
    java.update_config(client.config._conf["m2ee"], vcap_data, java_version)
    runtime.set_jetty_config(client)
    newrelic.update_config(client, vcap_data["application_name"])
    appdynamics.update_config(client, vcap_data["application_name"])
    runtime.set_application_name(client, vcap_data["application_name"])
    telegraf.update_config(client, vcap_data["application_name"])
    datadog.update_config(client)
    return client


@atexit.register
def terminate_process():
    if m2ee:
        logging.info("stopping app...")
        if not m2ee.stop():
            if not m2ee.terminate():
                m2ee.kill()
    try:
        this_process = os.getpgid(0)
        logging.debug(
            "Terminating process group with pgid=%s", format(this_process)
        )
        os.killpg(this_process, signal.SIGTERM)
        time.sleep(3)
        os.killpg(this_process, signal.SIGKILL)
    except OSError:
        logging.exception("Failed to terminate all child processes")


def set_up_instadeploy_if_deploy_password_is_set(m2ee_client):
    if os.getenv("DEPLOY_PASSWORD"):
        mx_version = m2ee_client.config.get_runtime_version()
        if util.use_instadeploy(mx_version):

            def reload_callback():
                m2ee_client.client.request("reload_model")

            def restart_callback():
                global app_is_restarting
                app_is_restarting = True
                if not m2ee_client.stop():
                    m2ee_client.terminate()
                runtime.complete_start_procedure_safe_to_use_for_restart(m2ee)
                app_is_restarting = False

            thread = instadeploy.InstaDeployThread(
                util.get_deploy_port(),
                restart_callback,
                reload_callback,
                mx_version,
                runtime.get_java_version(mx_version),
            )
            thread.setDaemon(True)
            thread.start()

            if os.path.exists(os.path.expanduser("~/.sourcepush")):
                instadeploy.send_metadata_to_cloudportal()
        else:
            logging.warning(
                "Not setting up InstaDeploy because this mendix "
                "runtime version %s does not support it",
                mx_version,
            )


def loop_until_process_dies(m2ee_client):
    while True:
        if app_is_restarting or m2ee_client.runner.check_pid():
            time.sleep(10)
        else:
            break
    emit(jvm={"crash": 1.0})
    logging.info("process died, stopping")
    sys.exit(1)


def emit(**stats):
    stats["version"] = "1.0"
    stats["timestamp"] = datetime.datetime.now().isoformat()
    logging.info("MENDIX-METRICS: %s", json.dumps(stats))


if __name__ == "__main__":

    logging.basicConfig(
        level=util.get_buildpack_loglevel(),
        stream=sys.stdout,
        format="%(levelname)s: %(message)s",
    )

    commit = util.get_current_buildpack_commit()
    if commit == "unknown_commit":
        logging.debug("Failed to read file", exc_info=True)
    logging.info(
        "Started Mendix Cloud Foundry Buildpack v%s [commit:%s]",
        BUILDPACK_VERSION,
        commit,
    )

    try:
        if os.getenv("CF_INSTANCE_INDEX") is None:
            logging.warning(
                "CF_INSTANCE_INDEX environment variable not found. Assuming "
                "responsibility for scheduled events execution and database "
                "synchronization commands."
            )
        pre_process_m2ee_yaml()
        runtime.activate_license()

        m2ee = set_up_m2ee_client(util.get_vcap_data())

        def sigterm_handler(_signo, _stack_frame):
            m2ee.stop()
            sys.exit(0)

        def sigusr_handler(_signo, _stack_frame):
            if _signo == signal.SIGUSR1:
                emit(jvm={"errors": 1.0})
            elif _signo == signal.SIGUSR2:
                emit(jvm={"ooms": 1.0})
            else:
                # Should not happen
                pass
            m2ee.stop()
            sys.exit(1)

        signal.signal(signal.SIGTERM, sigterm_handler)
        signal.signal(signal.SIGUSR1, sigusr_handler)
        signal.signal(signal.SIGUSR2, sigusr_handler)

        nginx.set_up_files(m2ee)
        telegraf.run()
        datadog.run(m2ee.config.get_runtime_version())
        runtime.run(m2ee)
        set_up_instadeploy_if_deploy_password_is_set(m2ee)
        runtime.run_components(m2ee)
        nginx_process = nginx.run()
        loop_until_process_dies(m2ee)
    except Exception:
        ex = traceback.format_exc()
        logging.error("Starting app container failed: %s", ex)
        callback_url = os.environ.get("BUILD_STATUS_CALLBACK_URL")
        if callback_url:
            requests.put(callback_url, ex)
        raise
