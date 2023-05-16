#!/usr/bin/env python3
import atexit
import logging
import os
import signal
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

from buildpack import databroker, util
from buildpack.databroker import business_events
from buildpack.core import java, nginx, runtime
from buildpack.infrastructure import database, storage
from buildpack.telemetry import (
    appdynamics,
    datadog,
    fluentbit,
    splunk,
    logs,
    metering,
    metrics,
    mx_java_agent,
    newrelic,
    telegraf,
    dynatrace,
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
                "Successfully sent [%s] to process group [%s]",
                signum.name,
                process_group,
            )
        except OSError as error:
            logging.debug(
                "Failed to send [%s] to process group [%s]: (OSError) %s",
                signum.name,
                process_group,
                error,
            )
        except SystemExit as error:
            # Workaround for UPV4-2859 - https://github.com/python/cpython/issues/103512#issuecomment-1541021187
            logging.debug(
                "Failed to send [%s] to process group [%s]: (SystemExit) %s",
                signum.name,
                process_group,
                error,
            )

    _kill_process_group_with_signal(signal.SIGTERM)


# Handler for child process signals
# Required to kill zombie processes
def _sigchild_handler(_signo, _stack_frame):
    os.waitpid(-1, os.WNOHANG)


# Handler for system termination signal (SIGTERM)
# This is required for Cloud Foundry:
# https://docs.cloudfoundry.org/devguide/deploy-apps/app-lifecycle.html#shutdown
def _sigterm_handler(_signo, _stack_frame):
    # Call sys.exit() so that all atexit handlers are explicitly called
    sys.exit()


# Handler for user signals (e.g. SIGUSR1 and SIGUSR2)
# These are specified as Java options in etc/m2ee/m2ee.yaml and handle e.g. OOM errors
# This handler is extensible and can incorporate handle_sigusr() calls
# in buildpack components
def _sigusr_handler(_signo, _stack_frame):
    # pylint: disable=no-member
    logging.debug("%s received", signal.Signals(_signo).name)
    metrics.handle_sigusr(_signo, _stack_frame)
    # Call sys.exit(1) so that all atexit handlers are explicitly called
    sys.exit(1)


def _register_signal_handlers():
    signal.signal(signal.SIGCHLD, _sigchild_handler)
    signal.signal(signal.SIGTERM, _sigterm_handler)
    signal.signal(signal.SIGUSR1, _sigusr_handler)
    signal.signal(signal.SIGUSR2, _sigusr_handler)


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
                "CF_INSTANCE_INDEX environment variable not found, "
                "assuming cluster leader responsibility..."
            )

        # Initialize the runtime
        m2ee = runtime.setup(util.get_vcap_data())

        # Get versions and names
        runtime_version = runtime.get_runtime_version()
        model_version = runtime.get_model_version()
        application_name = util.get_vcap_data()["application_name"]

        # Update runtime configuration based on component configuration
        database.update_config(m2ee)
        storage.update_config(m2ee)
        java.update_config(
            m2ee, application_name, util.get_vcap_data(), runtime_version
        )
        newrelic.update_config(m2ee, application_name)
        appdynamics.update_config(m2ee)
        dynatrace.update_config(m2ee)
        splunk.update_config(m2ee)
        fluentbit.update_config(m2ee)
        mx_java_agent.update_config(m2ee)
        telegraf.update_config(m2ee, application_name)
        (
            databroker_jmx_instance_cfg,
            databroker_jmx_config_files,
        ) = databroker_processes.get_datadog_config(datadog._get_user_checks_dir())
        datadog.update_config(
            m2ee,
            model_version=model_version,
            runtime_version=runtime_version,
            extra_jmx_instance_config=databroker_jmx_instance_cfg,
            jmx_config_files=databroker_jmx_config_files,
        )
        nginx.update_config()
        logging.debug(dir(databroker))
        logging.debug(dir(business_events))
        databroker.update_config(m2ee)
        business_events.update_config(m2ee, util.get_vcap_services_data())

        # Start components and runtime
        telegraf.run(runtime_version)
        datadog.run(model_version, runtime_version)
        fluentbit.run(model_version, runtime_version)
        metering.run()
        logs.run(m2ee)
        runtime.run(m2ee, logs.get_loglevels())
        metrics.run(m2ee)
        appdynamics.run()
        nginx.run()

        # Wait for the runtime to be ready before starting Databroker
        if databroker.is_enabled():
            runtime.await_database_ready(m2ee)
            databroker_processes.run(database.get_config())
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
