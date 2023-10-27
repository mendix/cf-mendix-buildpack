import logging
import os
import subprocess
import shutil
import socket
from typing import List, Tuple

import backoff

from buildpack import util
from buildpack.telemetry import newrelic, splunk
from lib.m2ee.util import strtobool

NAMESPACE = "fluentbit"
CONF_FILENAME = f"{NAMESPACE}.conf"
FILTER_FILENAMES = ("redaction.lua", "metadata.lua")
FLUENTBIT_ENV_VARS = {
    "FLUENTBIT_LOGS_PORT": os.getenv("FLUENTBIT_LOGS_PORT", default="5170"),
    "FLUENTBIT_LOG_LEVEL": os.getenv(
        "FLUENTBIT_LOG_LEVEL", default="info"
    ).lower(),
}


def _set_default_env(m2ee):
    for var_name, value in FLUENTBIT_ENV_VARS.items():
        util.upsert_custom_environment_variable(m2ee, var_name, value)


def _get_output_conf_filenames() -> List[str]:
    """
    Determine the output configs to use. Only enabled integrations
    will have the output file in the container.
    """
    output_conf_files: List[str] = []
    if splunk.is_splunk_enabled():
        output_conf_files.append("output_splunk.conf")
    if newrelic.is_enabled():
        output_conf_files.append("output_newrelic.conf")
    return output_conf_files


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

    output_conf_files = _get_output_conf_filenames()

    for filename in (
            CONF_FILENAME, *FILTER_FILENAMES, *output_conf_files
    ):
        shutil.copy(
            os.path.join(buildpack_dir, "etc", NAMESPACE, filename),
            os.path.join(destination_path, NAMESPACE),
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

    fluentbit_dir = os.path.join(os.path.abspath(".local"), NAMESPACE)
    fluentbit_bin_path = os.path.join(fluentbit_dir, "fluent-bit")
    fluentbit_config_path = os.path.join(fluentbit_dir, CONF_FILENAME)
    print_logs = _print_logs()

    if not os.path.exists(fluentbit_bin_path):
        logging.warning(
            "Fluent Bit is not installed yet. "
            "Please redeploy your application to complete "
            "Fluent Bit installation."
        )
        splunk.integration_complete(success=False)
        newrelic.integration_complete(success=False)
        return

    agent_environment = _set_up_environment(model_version, runtime_version)

    logging.info("Starting Fluent Bit...")
    subprocess.Popen(
        (fluentbit_bin_path, "-c", fluentbit_config_path, *print_logs),
        env=agent_environment,
    )

    # The runtime does not handle a non-open logs endpoint socket
    # gracefully, so wait until it's up
    @backoff.on_predicate(backoff.expo, lambda x: x > 0, max_time=120)
    def _await_logging_endpoint():
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(
            ("localhost", int(FLUENTBIT_ENV_VARS["FLUENTBIT_LOGS_PORT"]))
        )

    logging.info("Awaiting Fluent Bit log subscriber...")
    success = True
    if _await_logging_endpoint() != 0:
        success = False

    _integration_complete(success)
    splunk.integration_complete(success)
    newrelic.integration_complete(success)


def _integration_complete(success: bool) -> None:
    """Call when the setup is done."""
    if success:
        logging.info("Fluent Bit log subscriber is ready.")
    else:
        logging.error(
            "Fluent Bit log subscriber was not initialized correctly. "
            "Application logs will not be shipped to Fluent Bit."
        )


def _set_up_environment(model_version, runtime_version):
    fluentbit_env_vars = FLUENTBIT_ENV_VARS

    env_vars = dict(os.environ.copy())

    env_vars["FLUENTBIT_APP_HOSTNAME"] = util.get_hostname()
    env_vars["FLUENTBIT_APP_NAME"] = util.get_app_from_domain()
    env_vars["FLUENTBIT_APP_RUNTIME_VERSION"] = str(runtime_version)
    env_vars["FLUENTBIT_APP_MODEL_VERSION"] = model_version

    env_vars["LOGS_REDACTION"] = str(_is_logs_redaction_enabled())

    fluentbit_env_vars.update(env_vars)
    return fluentbit_env_vars


def is_fluentbit_enabled():
    """
    The function checks if some modules which requires
    Fluent Bit is configured.
    """
    return any(
        [splunk.is_splunk_enabled(), newrelic.is_enabled()]
    )  # Add other modules, where Fluent Bit is used


def _print_logs() -> Tuple:
    """Discard logs unless debug is active."""
    # FluentBit currently does not support log rotation, therefore
    # logs don't go to a file. If debug on, send to stdout
    if FLUENTBIT_ENV_VARS["FLUENTBIT_LOG_LEVEL"] == "debug":
        return tuple()
    return "-l", "/dev/null"


def _is_logs_redaction_enabled() -> bool:
    """Check if logs should be redacted."""

    # Use this, if it is set
    logs_redaction = os.getenv("LOGS_REDACTION")
    if logs_redaction is not None:
        return bool(strtobool(logs_redaction))

    # DEPRECATED - Splunk-specific LOGS_REDACTION variable
    if splunk.is_splunk_enabled():
        return bool(strtobool(os.getenv("SPLUNK_LOGS_REDACTION", "true")))

    # Turned on by default
    return True
