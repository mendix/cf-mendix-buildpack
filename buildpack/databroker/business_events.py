#
# [EXPERIMENTAL]
#
# Extract Business Events configuration from vcap services and create mx constants
#

CONSTANTS_PREFIX = "BusinessEvents"


def get_config(vcap_services):
    be_config = {}
    for service_name, service_creds in vcap_services.items():
        if "kafka" in service_name:
            kafka_creds = service_creds[0]["credentials"]
            for key, value in kafka_creds.items():
                be_config[f"{CONSTANTS_PREFIX}.{key}"] = value
    return be_config
