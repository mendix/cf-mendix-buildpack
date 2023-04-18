import logging
import os
import subprocess
import shutil
import socket

import backoff

from buildpack import util
from buildpack.telemetry import splunk


NAMESPACE = "fluentbit"
CONF_FILENAME = f"{NAMESPACE}.conf"
FILTER_FILENAMES = ("redaction.lua", "metadata.lua")
FLUENTBIT_ENV_VARS = {
    "FLUENTBIT_LOGS_PORT": os.getenv("FLUENTBIT_LOGS_PORT", default="5170"),
}


def _set_default_env(m2ee):
    for var_name, value in FLUENTBIT_ENV_VARS.items():
        util.upsert_custom_environment_variable(m2ee, var_name, value)


def stage(buildpack_dir, destination_path, cache_path):

    if not is_fluentbit_enabled():
        return

    util.resolve_dependency(
        "fluentbit",
        # destination_path - DOT_LOCAL_LOCATION
        os.path.join(destination_path, NAMESPACE),
        buildpack_dir=buildpack_dir,
        cache_dir=cache_path,
    )

    for filename in (CONF_FILENAME, *FILTER_FILENAMES):
        shutil.copy(
            os.path.join(buildpack_dir, "etc", NAMESPACE, filename),
            os.path.join(
                destination_path,
                NAMESPACE,
            ),
        )

    logging.info("Fluent Bit has been installed successfully.")


def update_config(m2ee):

    if not is_fluentbit_enabled():
        return

    _set_default_env(m2ee)

    util.upsert_logging_config(
        m2ee,
        {
            "type": "tcpjsonlines",
            "name": "FluentbitSubscriber",
            "autosubscribe": "INFO",
            "host": "localhost",
            "port": FLUENTBIT_ENV_VARS["FLUENTBIT_LOGS_PORT"],
        },
    )


def run(model_version, runtime_version):

    if not is_fluentbit_enabled():
        return

    fluentbit_dir = os.path.join(
        os.path.abspath(".local"),
        NAMESPACE,
    )

    fluentbit_bin_path = os.path.join(
        fluentbit_dir,
        "fluent-bit",
    )

    fluentbit_config_path = os.path.join(
        fluentbit_dir,
        CONF_FILENAME,
    )

    if not os.path.exists(fluentbit_bin_path):
        logging.warning(
            "Fluent Bit is not installed yet. "
            "Please redeploy your application to complete "
            "Fluent Bit installation."
        )
        splunk.print_failed_message()
        return

    agent_environment = _set_up_environment(model_version, runtime_version)

    logging.info("Starting Fluent Bit...")

    subprocess.Popen(
        (fluentbit_bin_path, "-c", fluentbit_config_path), env=agent_environment
    )

    # The runtime does not handle a non-open logs endpoint socket
    # gracefully, so wait until it's up
    @backoff.on_predicate(backoff.expo, lambda x: x > 0, max_time=10)
    def _await_logging_endpoint():
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(
            ("localhost", int(FLUENTBIT_ENV_VARS["FLUENTBIT_LOGS_PORT"]))
        )

    logging.info("Awaiting Fluent Bit log subscriber...")
    if _await_logging_endpoint() == 0:
        logging.info("Fluent Bit log subscriber is ready.")
        splunk.print_ready_message()
    else:
        logging.error(
            "Fluent Bit log subscriber was not initialized correctly."
            "Application logs will not be shipped to Fluent Bit."
        )
        splunk.print_failed_message()


def _set_up_environment(model_version, runtime_version):
    env_vars = dict(os.environ.copy())

    env_vars["SPLUNK_APP_HOSTNAME"] = util.get_hostname()
    env_vars["SPLUNK_APP_NAME"] = util.get_app_from_domain()
    env_vars["SPLUNK_APP_RUNTIME_VERSION"] = str(runtime_version)
    env_vars["SPLUNK_APP_MODEL_VERSION"] = model_version

    return env_vars


def is_fluentbit_enabled():
    """
    The function checks if some modules which requires
    Fluent Bit is configured.

    """

    return any(
        [splunk.is_splunk_enabled()]
    )  # Add other modules, where Fluent Bit is used
