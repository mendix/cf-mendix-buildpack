import logging
import os
from buildpack import util


SPLUNK_ENV_VARS = {
    "SPLUNK_PORT": os.getenv("SPLUNK_PORT", default="8088"),
}

REQUIRED_SPLUNK_ENV_VARS = ["SPLUNK_HOST", "SPLUNK_TOKEN"]


def _set_default_env(m2ee):
    for var_name, value in SPLUNK_ENV_VARS.items():
        util.upsert_custom_environment_variable(m2ee, var_name, value)


def stage():

    if not is_splunk_enabled():
        return

    logging.info("Configuring Splunk ...")


def update_config(m2ee):

    if not is_splunk_enabled():
        return

    _set_default_env(m2ee)


def integration_complete(success: bool) -> None:
    """
    This function can be called from external module.
    For example: fluentbit.py calls this function when Fluent Bit is done.
    """
    if not is_splunk_enabled():
        return

    if success:
        logging.info("Splunk has been configured successfully.")
    else:
        logging.error("Failed to configure Splunk.")


def is_splunk_enabled():
    """
    The function checks if all environment variables
    are set up which are required for Splunk connection.

    """

    return all(map(os.getenv, REQUIRED_SPLUNK_ENV_VARS))
