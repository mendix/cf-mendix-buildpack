#
# [EXPERIMENTAL]
#
# Extract Business Events configuration from vcap services and create mx constants
#

import logging

from buildpack import util

CONSTANTS_PREFIX = "BusinessEvents"


def update_config(m2ee, vcap_services_data):
    # append Business Events config to MicroflowConstants dict
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
                    for key, value in kafka_creds.items():
                        be_config[f"{CONSTANTS_PREFIX}.{key}"] = value
                else:
                    logging.error("Business Events: configuration is empty")
    except Exception as ex:
        logging.error(
            "Business Events: error reading deployment configuration "
            + str(ex)
        )

    return be_config
