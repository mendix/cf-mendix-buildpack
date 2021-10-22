import logging
import os

from buildpack import util

AGENT_VERSION = "6.2.1"
NAMESPACE = "newrelic"
ROOT_DIR = ".local"


def stage(install_path, cache_path):
    if get_new_relic_license_key():
        util.download_and_unpack(
            util.get_blobstore_url(
                "/mx-buildpack/newrelic/newrelic-java-{}.zip".format(
                    AGENT_VERSION
                )
            ),
            _get_destination_dir(install_path),
            cache_path,
        )


def _get_destination_dir(dot_local=ROOT_DIR):
    return os.path.abspath(os.path.join(dot_local, NAMESPACE))


def update_config(m2ee, app_name):
    if get_new_relic_license_key() is None:
        logging.debug(
            "Skipping New Relic setup, no license key found in environment"
        )
        return
    logging.info("Adding new relic")
    m2ee_section = m2ee.config._conf["m2ee"]
    if "custom_environment" not in m2ee_section:
        m2ee_section["custom_environment"] = {}
    m2ee_section["custom_environment"][
        "NEW_RELIC_LICENSE_KEY"
    ] = get_new_relic_license_key()
    m2ee_section["custom_environment"]["NEW_RELIC_APP_NAME"] = app_name
    m2ee_section["custom_environment"]["NEW_RELIC_LOG"] = os.path.join(
        _get_destination_dir(), "newrelic", "agent.log"
    )

    m2ee.config._conf["m2ee"]["javaopts"].append(
        "-javaagent:{}".format(
            os.path.join(_get_destination_dir(), "newrelic", "newrelic.jar")
        )
    )


def get_new_relic_license_key():
    vcap_services = util.get_vcap_services_data()
    if vcap_services and "newrelic" in vcap_services:
        return vcap_services["newrelic"][0]["credentials"]["licenseKey"]
    return None
