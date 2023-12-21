import logging
import os
import subprocess
from buildpack import util
from lib.m2ee.util import strtobool


APPDYNAMICS_INSTALL_PATH = os.path.abspath(".local/appdynamics/")
APPDYNAMICS_JAVAAGENT_PATH = os.path.join(APPDYNAMICS_INSTALL_PATH, "javaagent.jar")

APPDYNAMICS_MACHINE_AGENT_PATH = os.path.join(
    APPDYNAMICS_INSTALL_PATH,
    "machineagent",
    "bin",
    "machine-agent",
)

CF_APPLICATION_INDEX = int(os.getenv("CF_INSTANCE_INDEX", default="0"))
CF_APPLICATION_NAME = util.get_vcap_data()["application_name"]

APPDYNAMICS_ENV_VARS = {
    "APPDYNAMICS_AGENT_APPLICATION_NAME": os.getenv(
        "APPDYNAMICS_AGENT_APPLICATION_NAME",
        default=util.get_app_from_domain(),
    ),
    "APPDYNAMICS_AGENT_NODE_NAME": f"{os.getenv('APPDYNAMICS_AGENT_NODE_NAME', default='node')}-{CF_APPLICATION_INDEX}",  # noqa: C0301
    "APPDYNAMICS_AGENT_TIER_NAME": os.getenv(
        "APPDYNAMICS_AGENT_TIER_NAME", default=CF_APPLICATION_NAME
    ),
    "APPDYNAMICS_CONTROLLER_PORT": os.getenv(
        "APPDYNAMICS_CONTROLLER_PORT", default="443"
    ),
    "APPDYNAMICS_CONTROLLER_SSL_ENABLED": os.getenv(
        "APPDYNAMICS_CONTROLLER_SSL_ENABLED", default="true"
    ),
    "APPDYNAMICS_AGENT_UNIQUE_HOST_ID": f"{os.getenv('APPDYNAMICS_AGENT_UNIQUE_HOST_ID', default=CF_APPLICATION_NAME),}-{CF_APPLICATION_INDEX}",  # noqa: C0301
}


def _set_default_env(m2ee):
    for var_name, value in APPDYNAMICS_ENV_VARS.items():
        util.upsert_custom_environment_variable(m2ee, var_name, value)


def stage(buildpack_dir, destination_path, cache_path):
    if appdynamics_used():
        util.resolve_dependency(
            "appdynamics.agent",
            # destination_path - DOT_LOCAL_LOCATION
            destination_path + "/appdynamics/",
            buildpack_dir=buildpack_dir,
            cache_dir=cache_path,
        )

        if machine_agent_enabled():
            util.resolve_dependency(
                "appdynamics.machine-agent",
                destination_path + "/appdynamics/machineagent/",
                buildpack_dir=buildpack_dir,
                cache_dir=cache_path,
            )


def update_config(m2ee):
    if not appdynamics_used():
        return

    if not _is_javaagent_installed():
        logging.warning(
            "AppDynamics Java Agent isn't installed yet. "
            "Please redeploy your application to complete "
            "AppDynamics Java Agent installation."
        )
        return

    logging.info("AppDynamics Java Agent env. variables are configured. Starting...")

    util.upsert_javaopts(
        m2ee,
        [
            f"-javaagent:{APPDYNAMICS_JAVAAGENT_PATH}",
            f"-Dappagent.install.dir={APPDYNAMICS_INSTALL_PATH}",
        ],
    )

    _set_default_env(m2ee)


def run():
    if not machine_agent_enabled():
        return

    if not _is_machine_agent_installed():
        logging.warning(
            "AppDynamics Machine Agent isn't installed yet. "
            "Please redeploy your application to complete "
            "AppDynamics Machine Agent installation."
        )
        return

    logging.info("AppDynamics Machine Agent env. variable is configured. Starting...")
    env_dict = dict(os.environ)
    env_dict.update(APPDYNAMICS_ENV_VARS)
    subprocess.Popen(
        (APPDYNAMICS_MACHINE_AGENT_PATH, "-Dmetric.http.listener=true"),
        env=env_dict,
    )


def _is_javaagent_installed():
    return os.path.exists(APPDYNAMICS_JAVAAGENT_PATH)


def _is_machine_agent_installed():
    return os.path.exists(APPDYNAMICS_MACHINE_AGENT_PATH)


def appdynamics_used():
    """
    The function checks if all required AppDynamics related
    environment variables are set.

    """
    required_envs = {
        "APPDYNAMICS_AGENT_ACCOUNT_ACCESS_KEY",
        "APPDYNAMICS_AGENT_ACCOUNT_NAME",
        "APPDYNAMICS_CONTROLLER_HOST_NAME",
    }

    os_env_set = set(os.environ)

    diff_envs = required_envs.difference(os_env_set)

    if len(diff_envs) == 0:
        return True
    return False


def machine_agent_enabled():
    """
    The function checks if the corresponding environment
    variable for AppDynamics Machine Agent is True.

    """
    if not appdynamics_used():
        return False

    is_machine_agent_enabled = strtobool(
        os.getenv("APPDYNAMICS_MACHINE_AGENT_ENABLED", default="false")
    )

    return is_machine_agent_enabled
