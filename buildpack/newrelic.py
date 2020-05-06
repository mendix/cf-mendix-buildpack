import logging
import os
import shutil

from buildpack import util


def compile(buildpack_path, build_path):
    if get_new_relic_license_key():
        shutil.copytree(
            os.path.join(buildpack_path, "vendor/newrelic"),
            os.path.join(build_path, "newrelic"),
        )


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
    m2ee_section["custom_environment"]["NEW_RELIC_LOG"] = os.path.abspath(
        "newrelic/agent.log"
    )

    m2ee.config._conf["m2ee"]["javaopts"].append(
        "-javaagent:{path}".format(
            path=os.path.abspath("newrelic/newrelic.jar")
        )
    )


def get_new_relic_license_key():
    vcap_services = util.get_vcap_services_data()
    if vcap_services and "newrelic" in vcap_services:
        return vcap_services["newrelic"][0]["credentials"]["licenseKey"]
    return None
