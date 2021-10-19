import logging
import os

from buildpack import util

AGENT_VERSION = "6.2.1"
NAMESPACE = "newrelic"
ROOT_DIR = ".local"


def stage(buildpack_dir, install_path, cache_path):
    if get_new_relic_license_key():
        util.resolve_dependency(
            util.get_blobstore_url(
                "/mx-buildpack/newrelic/newrelic-java-{}.zip".format(
                    AGENT_VERSION
                )
            ),
            _get_destination_dir(install_path),
            buildpack_dir=buildpack_dir,
            cache_dir=cache_path,
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

    util.upsert_custom_environment_variable(
        m2ee, "NEW_RELIC_LICENSE_KEY", get_new_relic_license_key()
    )
    util.upsert_custom_environment_variable(
        m2ee, "NEW_RELIC_APP_NAME", app_name
    )
    util.upsert_custom_environment_variable(
        m2ee,
        "NEW_RELIC_LOG",
        os.path.join(_get_destination_dir(), "newrelic", "agent.log"),
    )

    util.upsert_javaopts(
        m2ee,
        "-javaagent:{}".format(
            os.path.join(_get_destination_dir(), "newrelic", "newrelic.jar")
        ),
    )


def get_new_relic_license_key():
    vcap_services = util.get_vcap_services_data()
    if vcap_services and "newrelic" in vcap_services:
        return vcap_services["newrelic"][0]["credentials"]["licenseKey"]
    return None
