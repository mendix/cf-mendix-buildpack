#
# [EXPERIMENTAL]
#
# Extract Business Events configuration from vcap services and create mx constants
#

from buildpack import util

import logging
import requests

CONSTANTS_PREFIX = "BusinessEvents"

DEDICATED_PLAN_CONSTANTS = [
    "ServerUrl",
    "UserName",
    "Password",
    "ClientConfiguration",
]
CLIENT_CONFIG_URL_KEY = "ClientConfigUrl"


def update_config(m2ee, vcap_services_data):
    # if kafka is present in vcap services upsert Business Events constants
    util.upsert_microflow_constants(m2ee, _get_config(vcap_services_data))
    logging.debug("Business Events config added to MicroflowConstants")


def _get_config(vcap_services):
    be_config = {}
    try:
        for service_name, service_creds in vcap_services.items():
            if "kafka" in service_name:
                if len(service_creds) > 1:
                    logging.warning(
                        "Business Events: multiple configurations found for kafka."
                        + "Using the first config from list"
                    )
                if (
                    "credentials" in service_creds[0]
                    and service_creds[0]["credentials"]
                ):
                    kafka_creds = service_creds[0]["credentials"]
                    if "ChannelName" in kafka_creds:
                        for key, value in kafka_creds.items():
                            be_config[f"{CONSTANTS_PREFIX}.{key}"] = value
                    elif CLIENT_CONFIG_URL_KEY in kafka_creds:
                        auth_token = kafka_creds.get(
                            "ClientConfigAuthToken", ""
                        )
                        headers = {"Authorization": f"Bearer {auth_token}"}
                        resp = requests.get(
                            url=kafka_creds.get(CLIENT_CONFIG_URL_KEY, ""),
                            headers=headers,
                            timeout=30,
                        )
                        resp.raise_for_status()
                        for constant in DEDICATED_PLAN_CONSTANTS:
                            be_config[
                                f"{CONSTANTS_PREFIX}.{constant}"
                            ] = kafka_creds.get(constant, "")
                        be_config[
                            f"{CONSTANTS_PREFIX}.ClientConfiguration"
                        ] = resp.text
                else:
                    logging.error("Business Events: configuration is empty")
    except Exception as ex:
        logging.error(
            "Business Events: error reading deployment configuration "
            + str(ex)
        )

    return be_config
