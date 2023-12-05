import logging
import os
from typing import Dict, Optional

from buildpack import util

NAMESPACE = "newrelic"
ROOT_DIR = ".local"

REQUIRED_NEW_RELIC_ENV_VARS = [
    "NEW_RELIC_LICENSE_KEY", "NEW_RELIC_LOGS_URI", "NEW_RELIC_METRICS_URI"
]
NEW_RELIC_ENV_VARS = {
    "NEW_RELIC_APP_NAME": os.getenv(
        "NEW_RELIC_APP_NAME", util.get_app_from_domain()
    ),
    "NEW_RELIC_LOG": os.path.join(
        os.path.abspath(os.path.join(ROOT_DIR, NAMESPACE)),
        "newrelic",
        "agent.log",
    ),
}


def _set_default_env(m2ee):
    for var_name, value in NEW_RELIC_ENV_VARS.items():
        util.upsert_custom_environment_variable(m2ee, var_name, value)


def stage(buildpack_dir, install_path, cache_path):
    if _get_new_relic_license_key():
        util.resolve_dependency(
            f"{NAMESPACE}.agent",
            _get_destination_dir(install_path),
            buildpack_dir=buildpack_dir,
            cache_dir=cache_path,
        )


def _get_destination_dir(dot_local=ROOT_DIR):
    return os.path.abspath(os.path.join(dot_local, NAMESPACE))


def update_config(m2ee, app_name):
    if _get_new_relic_license_key() is None:
        logging.debug("Skipping New Relic setup, no license key found in environment")
        return

    util.upsert_custom_environment_variable(
        m2ee, "NEW_RELIC_LICENSE_KEY", _get_new_relic_license_key()
    )

    _set_default_env(m2ee)

    util.upsert_javaopts(
        m2ee,
        [
            f"-javaagent:{os.path.join(_get_destination_dir(), 'newrelic', 'newrelic.jar')}",  # noqa: C0301
            f"-Dnewrelic.config.labels=\"{_get_labels(app_name)}\"",
        ]
    )


def _get_new_relic_license_key() -> Optional[str]:
    """Get the New Relic's license key."""
    # DEPRECATED - Service-binding integration (on-prem only)
    vcap_services = util.get_vcap_services_data()
    if vcap_services and "newrelic" in vcap_services:
        return vcap_services["newrelic"][0]["credentials"]["licenseKey"]

    return os.getenv("NEW_RELIC_LICENSE_KEY", None)


def is_enabled() -> bool:
    """
    The function checks if all environment variables required
    for New Relic connection are set up. The service-binding
    based integration (on-prem only) does not care about this.
    """
    return all(map(os.getenv, REQUIRED_NEW_RELIC_ENV_VARS))


def get_metrics_config() -> Dict:
    """Configs to be used by telegraf."""
    return {
        "api_key": os.getenv("NEW_RELIC_LICENSE_KEY", default=""),
        "metrics_base_url": os.getenv("NEW_RELIC_METRICS_URI", default=""),
    }


def _get_labels(app_name) -> str:
    """Labels (tags) to be used by New Relic agent."""
    tags = get_metrics_tags(app_name)
    string_tags = ";".join([f"{k}:{v}" for k, v in tags.items()])
    return string_tags


def get_metrics_tags(app_name) -> Dict:
    """Tags to be used by telegraf."""
    return {
        "application_name": util.get_app_from_domain(),
        "instance_index": int(os.getenv("CF_INSTANCE_INDEX", "0")),
        "environment_id": app_name,
        "hostname": util.get_hostname()
    }


def integration_complete(success: bool) -> None:
    """Call when the setup is done."""
    if not is_enabled():
        return

    if success:
        logging.info("New Relic has been configured successfully.")
    else:
        logging.error("Failed to configure New Relic.")
