#!/usr/bin/env python3
import atexit
import logging
import os
import signal
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

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


# Exit handler to kill process group
@atexit.register
def _kill_process_group():
    logging.debug("Terminating process group...")

    def _kill_process_group_with_signal(signum):
        try:
            process_group = os.getpgrp()
            os.killpg(process_group, signum)
            logging.debug(
                "Successfully sent [{}] to process group [{}]".format(
                    signum.name, process_group
                ),
            )
        except OSError as error:
            logging.debug(
                "Failed to send [{}] to process group [{}]: {}".format(
                    signum.name, process_group, error
                )
            )

    _kill_process_group_with_signal(signal.SIGTERM)


# Handler for child process signals
# Required to kill zombie processes
def _sigchild_handler(_signo, _stack_frame):
    os.waitpid(-1, os.WNOHANG)


# Handler for system termination signal (SIGTERM)
# This is required for Cloud Foundry: https://docs.cloudfoundry.org/devguide/deploy-apps/app-lifecycle.html#shutdown
def _sigterm_handler(_signo, _stack_frame):
    # Call sys.exit() so that all atexit handlers are explicitly called
    sys.exit()


def _register_signal_handlers():
    signal.signal(signal.SIGCHLD, _sigchild_handler)
    signal.signal(signal.SIGTERM, _sigterm_handler)


if os.environ.get("DEBUG_CONTAINER", "false").lower() == "true":
    logging.warning(Maintenance.MESSAGE)
    port = int(os.environ.get("PORT", 8080))
    httpd = HTTPServer(("", port), Maintenance)
    httpd.serve_forever()


if __name__ == "__main__":
    m2ee = None
    nginx_process = None
    databroker_processes = databroker.Databroker()

    _register_signal_handlers()

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
                "CF_INSTANCE_INDEX environment variable not found, assuming cluster leader responsibility..."
            )

        # Set environment variables that the runtime needs for initial setup
        if databroker.is_enabled():
            os.environ[
                "MXRUNTIME_{}".format(databroker.RUNTIME_DATABROKER_FLAG)
            ] = "true"

        # Initialize the runtime
        m2ee = runtime.setup(util.get_vcap_data())

        # Get versions
        runtime_version = runtime.get_version(os.path.abspath("."))
        java_version = runtime.get_java_version(runtime_version)["version"]
        model_version = runtime.get_model_version(os.path.abspath("."))

        # Update runtime configuration based on component configuration
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
            model_version=model_version,
            runtime_version=runtime_version,
            extra_jmx_instance_config=databroker_jmx_instance_cfg,
            jmx_config_files=databroker_jmx_config_files,
        )
        nginx.configure(m2ee)

        # Start components and runtime
        telegraf.run()
        datadog.run(model_version, runtime_version)
        metering.run()
        nginx.run()
        runtime.run(m2ee)

        # Wait for the runtime to be ready before starting Databroker
        if databroker.is_enabled():
            runtime.await_database_ready(m2ee)
            databroker_processes.run(runtime.database.get_config())
    except RuntimeError as re:
        # Only the runtime throws RuntimeErrors (no pun intended)
        # Don't use the stack trace for these
        logging.error("Starting application failed: %s", re)
        sys.exit(1)
    except Exception:
        ex = traceback.format_exc()
        logging.error("Starting application failed. %s", ex)
        sys.exit(1)

    # Wait loop for runtime termination
    runtime.await_termination(m2ee)
