#
# [EXPERIMENTAL]
#
# Extract Business Events configuration from vcap services and create mx constants
#

import logging

from buildpack import util

CONSTANTS_PREFIX = "BusinessEvents"


def update_config(m2ee, vcap_services_data):
    business_events_cfg = _get_config(vcap_services_data)
    # append Business Events config to MicroflowConstants dict
    m2ee.config._conf["mxruntime"]["MicroflowConstants"].update(
        business_events_cfg
    )
    logging.debug("Business Events config added to MicroflowConstants")


def _get_config(vcap_services):
    be_config = {}
    for service_name, service_creds in vcap_services.items():
        if "kafka" in service_name:
            kafka_creds = service_creds[0]["credentials"]
            for key, value in kafka_creds.items():
                be_config[f"{CONSTANTS_PREFIX}.{key}"] = value
    return be_config
