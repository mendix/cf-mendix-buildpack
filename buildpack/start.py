#!/usr/bin/env python3
import atexit
import logging
import os
import signal
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

import backoff

from buildpack import (
    appdynamics,
    databroker,
    datadog,
    dynatrace,
    java,
    metering,
    mx_java_agent,
    newrelic,
    nginx,
    runtime,
    telegraf,
    util,
)
from buildpack.runtime_components import metrics


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


if __name__ == "__main__":
    m2ee = None
    nginx_process = None
    databroker_processes = databroker.Databroker()

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
        mx_java_agent.update_config(m2ee)
        telegraf.update_config(m2ee, util.get_vcap_data()["application_name"])
        (
            databroker_jmx_instance_cfg,
            databroker_jmx_config_files,
        ) = databroker_processes.get_datadog_config(
            datadog._get_user_checks_dir()
        )
        datadog.update_config(
            m2ee,
            extra_jmx_instance_config=databroker_jmx_instance_cfg,
            jmx_config_files=databroker_jmx_config_files,
        )
        nginx.configure(m2ee)

        @atexit.register
        def terminate_process():
            if m2ee:
                runtime.shutdown(m2ee, 10)
            else:
                logging.warning(
                    "Cannot terminate runtime: M2EE client not set"
                )
            databroker_processes.stop()
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
            databroker_processes.stop()
            sys.exit(0)

        def sigusr_handler(_signo, _stack_frame):
            logging.debug("Handling SIGUSR...")
            if _signo == signal.SIGUSR1:
                metrics.emit(jvm={"errors": 1.0})
            elif _signo == signal.SIGUSR2:
                metrics.emit(jvm={"ooms": 1.0})
            else:
                # Should not happen
                pass
            runtime.stop(m2ee)
            databroker_processes.stop()
            sys.exit(1)

        def sigchild_handler(_signo, _stack_frame):
            logging.debug("Handling SIGCHILD...")
            os.waitpid(-1, os.WNOHANG)

        signal.signal(signal.SIGCHLD, sigchild_handler)
        signal.signal(signal.SIGTERM, sigterm_handler)
        signal.signal(signal.SIGUSR1, sigusr_handler)
        signal.signal(signal.SIGUSR2, sigusr_handler)

        telegraf.run()
        datadog.run()
        metering.run()

        runtime.run(m2ee)
        runtime.run_components(m2ee)

        nginx_process = nginx.run()
        databroker_processes.run(m2ee, runtime.database.get_config())

        def loop_until_process_dies():
            @backoff.on_predicate(backoff.constant, interval=10, logger=None)
            def _await_process_dies():
                success = (
                    databroker_processes.restart_if_any_component_not_healthy()
                )
                if not success:
                    runtime.stop(m2ee)
                    return True
                return not m2ee.runner.check_pid()

            logging.debug("Waiting until runtime process dies...")
            _await_process_dies()

        loop_until_process_dies()

        metrics.emit(jvm={"crash": 1.0})
        logging.info("Runtime process stopped, stopping container...")

    except Exception:
        ex = traceback.format_exc()
        logging.error("Starting application failed: %s", ex)
        raise
