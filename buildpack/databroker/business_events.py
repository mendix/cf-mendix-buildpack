#
# [EXPERIMENTAL]
#
# Extract Business Events configuration from vcap services and create mx constants
#

from buildpack import util

import logging
import requests

CONSTANTS_PREFIX = "BusinessEvents"

BE_CONSTANTS_TO_INJECT = [
    "ServerUrl",
    "UserName",
    "Password",
    "ClientConfiguration",
]

OPTIONAL_CONSTANT_APPLY_LIMITS = "ApplyLimits"

CLIENT_CONFIG_URL_KEY = "ClientConfigUrl"


def update_config(m2ee, vcap_services_data):
    # if kafka is present in vcap services upsert Business Events constants
    existing_constants = util.get_microflow_constants(m2ee)
    be_config = _get_config(vcap_services_data, existing_constants)
    util.upsert_microflow_constants(m2ee, be_config)
    logging.debug("Business Events config added to MicroflowConstants")


def _get_client_config(url, auth_token, version):
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "X-Version": version,
    }

    resp = requests.get(
        url=url,
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def _configure_business_events_metrics(be_config, existing_constants):
    if f"{CONSTANTS_PREFIX}.GenerateMetrics" in existing_constants:
        if util.is_free_app():
            be_config[f"{CONSTANTS_PREFIX}.GenerateMetrics"] = "false"
            be_config[f"{CONSTANTS_PREFIX}.EnableHeartbeat"] = "false"
        else:
            be_config[f"{CONSTANTS_PREFIX}.GenerateMetrics"] = "true"
            be_config[f"{CONSTANTS_PREFIX}.EnableHeartbeat"] = "true"


def _get_config(vcap_services, existing_constants):
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
                    if CLIENT_CONFIG_URL_KEY in kafka_creds:
                        auth_token = kafka_creds.get("ClientConfigAuthToken", "")
                        for constant in BE_CONSTANTS_TO_INJECT:
                            be_config[
                                f"{CONSTANTS_PREFIX}.{constant}"
                            ] = kafka_creds.get(constant, "")
                        client_config = _get_client_config(
                            kafka_creds.get(CLIENT_CONFIG_URL_KEY, ""),
                            auth_token,
                            "1",
                        )
                        be_config[
                            f"{CONSTANTS_PREFIX}.ClientConfiguration"
                        ] = client_config
                        if kafka_creds.get(OPTIONAL_CONSTANT_APPLY_LIMITS):
                            be_config[
                                f"{CONSTANTS_PREFIX}.{OPTIONAL_CONSTANT_APPLY_LIMITS}"
                            ] = kafka_creds.get(OPTIONAL_CONSTANT_APPLY_LIMITS)
                    else:
                        logging.error(
                            "Business Events: configuration is not compatible, please unbind and bind the service again"
                        )
                else:
                    logging.error("Business Events: configuration is empty")

                # Update Business Events constants for metrics
                _configure_business_events_metrics(be_config, existing_constants)
    except Exception as ex:
        logging.error(
            "Business Events: error reading deployment configuration " + str(ex)
        )

    return be_config
