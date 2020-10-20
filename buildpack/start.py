#!/usr/bin/env python3
import atexit
import datetime
import json
import logging
import os
import signal
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

import backoff
import requests

from buildpack import (
    appdynamics,
    dynatrace,
    datadog,
    instadeploy,
    java,
    newrelic,
    nginx,
    runtime,
    telegraf,
    util,
)


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


def emit(**stats):
    stats["version"] = "1.0"
    stats["timestamp"] = datetime.datetime.now().isoformat()
    logging.info("MENDIX-METRICS: %s", json.dumps(stats))


if __name__ == "__main__":
    app_is_restarting = False
    m2ee = None
    nginx_process = None

    logging.basicConfig(
        level=util.get_buildpack_loglevel(),
        stream=sys.stdout,
        format="%(levelname)s: %(message)s",
    )

    logging.info(
        "Mendix Cloud Foundry Buildpack %s [%s] starting...",
        util.get_buildpack_version(),
        util.get_current_buildpack_commit(),
    )

    try:
        if os.getenv("CF_INSTANCE_INDEX") is None:
            logging.warning(
                "CF_INSTANCE_INDEX environment variable not found. Assuming "
                "responsibility for scheduled events execution and database "
                "synchronization commands."
            )
        runtime.pre_process_m2ee_yaml()
        runtime.activate_license()

        m2ee = runtime.set_up_m2ee_client(util.get_vcap_data())

        java_version = runtime.get_java_version(
            m2ee.config.get_runtime_version()
        )["version"]
        java.update_config(
            m2ee.config._conf["m2ee"], util.get_vcap_data(), java_version
        )

        newrelic.update_config(m2ee, util.get_vcap_data()["application_name"])
        appdynamics.update_config(
            m2ee, util.get_vcap_data()["application_name"]
        )
        dynatrace.update_config(m2ee, util.get_vcap_data()["application_name"])
        telegraf.update_config(m2ee, util.get_vcap_data()["application_name"])
        datadog.update_config(m2ee)

        @atexit.register
        def terminate_process():
            if m2ee:
                runtime.shutdown(m2ee, 10)
            else:
                logging.warning(
                    "Cannot terminate runtime: M2EE client not set"
                )
            try:
                process_group = os.getpgrp()
                logging.debug(
                    "Terminating process group with PGID [%s]",
                    format(process_group),
                )
                os.killpg(process_group, signal.SIGTERM)
                time.sleep(3)
                logging.debug(
                    "Killing process group with PGID [%s]",
                    format(process_group),
                )
                os.killpg(process_group, signal.SIGKILL)
            except OSError as error:
                logging.debug(
                    "Failed to terminate or kill complete process group: {}".format(
                        error
                    )
                )

        def sigterm_handler(_signo, _stack_frame):
            logging.debug("Handling SIGTERM...")
            runtime.stop(m2ee)
            sys.exit(0)

        def sigusr_handler(_signo, _stack_frame):
            logging.debug("Handling SIGUSR...")
            if _signo == signal.SIGUSR1:
                emit(jvm={"errors": 1.0})
            elif _signo == signal.SIGUSR2:
                emit(jvm={"ooms": 1.0})
            else:
                # Should not happen
                pass
            runtime.stop(m2ee)
            sys.exit(1)

        def sigchild_handler(_signo, _stack_frame):
            logging.debug("Handling SIGCHILD...")
            os.waitpid(-1, os.WNOHANG)

        signal.signal(signal.SIGCHLD, sigchild_handler)
        signal.signal(signal.SIGTERM, sigterm_handler)
        signal.signal(signal.SIGUSR1, sigusr_handler)
        signal.signal(signal.SIGUSR2, sigusr_handler)

        nginx.configure(m2ee)
        telegraf.run()
        datadog.run(m2ee.config.get_runtime_version())

        runtime.run(m2ee)

        def reload_callback():
            m2ee.client.request("reload_model")

        def restart_callback():
            global app_is_restarting

            if not m2ee:
                logging.warning("M2EE client not set")
            app_is_restarting = True
            if not runtime.shutdown(m2ee, 10):
                logging.warning("Could not kill runtime with M2EE")
            runtime.complete_start_procedure_safe_to_use_for_restart(m2ee)
            app_is_restarting = False

        instadeploy.set_up_instadeploy_if_deploy_password_is_set(
            reload_callback,
            restart_callback,
            m2ee.config.get_runtime_version(),
            runtime.get_java_version(m2ee.config.get_runtime_version()),
        )
        runtime.run_components(m2ee)

        nginx_process = nginx.run()

        def loop_until_process_dies():
            @backoff.on_predicate(backoff.constant, interval=10, logger=None)
            def _await_process_dies():
                return not (app_is_restarting or m2ee.runner.check_pid())

            logging.debug("Waiting until runtime process dies...")
            _await_process_dies()

        loop_until_process_dies()

        emit(jvm={"crash": 1.0})
        logging.info("Runtime process stopped, stopping container...")

    except Exception:
        ex = traceback.format_exc()
        logging.error("Starting application failed: %s", ex)
        callback_url = os.environ.get("BUILD_STATUS_CALLBACK_URL")
        if callback_url:
            requests.put(callback_url, ex)
        raise
