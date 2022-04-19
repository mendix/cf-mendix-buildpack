import logging
import os
import subprocess
from distutils.util import strtobool
from buildpack import util

APPDYNAMICS_VERSION = "22.1.0"

APPDYNAMICS_INSTALL_PATH = os.path.abspath(".local/appdynamics/")
APPDYNAMICS_JAVAAGENT_PATH = os.path.join(
    APPDYNAMICS_INSTALL_PATH, "javaagent.jar"
)

APPDYNAMICS_MACHINE_AGENT_PATH = os.path.join(
    APPDYNAMICS_INSTALL_PATH,
    "machineagent",
    "bin",
    "machine-agent",
)


def stage(buildpack_dir, destination_path, cache_path):
    if appdynamics_used():
        util.resolve_dependency(
            util.get_blobstore_url(
                "/mx-buildpack/appdynamics/appdynamics-agent-1.8-{}.zip".format(
                    APPDYNAMICS_VERSION
                )
            ),
            # destination_path - DOT_LOCAL_LOCATION
            destination_path + "/appdynamics/",
            buildpack_dir=buildpack_dir,
            cache_dir=cache_path,
        )

        if machine_agent_enabled():
            util.resolve_dependency(
                util.get_blobstore_url(
                    "/mx-buildpack/appdynamics/appdynamics-machineagent-bundle-{}.zip".format(
                        APPDYNAMICS_VERSION
                    )
                ),
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

    logging.info("Configuring AppDynamics.")

    util.upsert_javaopts(
        m2ee,
        [
            "-javaagent:{path}".format(path=APPDYNAMICS_JAVAAGENT_PATH),
            "-Dappagent.install.dir={path}".format(
                path=APPDYNAMICS_INSTALL_PATH
            ),
        ],
    )

    APPDYNAMICS_AGENT_NODE_NAME = "APPDYNAMICS_AGENT_NODE_NAME"
    if os.getenv(APPDYNAMICS_AGENT_NODE_NAME):
        util.upsert_custom_environment_variable(
            m2ee,
            APPDYNAMICS_AGENT_NODE_NAME,
            "%s-%s"
            % (
                os.getenv(APPDYNAMICS_AGENT_NODE_NAME),
                os.getenv("CF_INSTANCE_INDEX", "0"),
            ),
        )


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

    logging.info("Starting the AppDynamics Machine Agent...")
    env_dict = dict(os.environ)
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
        "APPDYNAMICS_AGENT_APPLICATION_NAME",
        "APPDYNAMICS_AGENT_NODE_NAME",
        "APPDYNAMICS_AGENT_TIER_NAME",
        "APPDYNAMICS_CONTROLLER_PORT",
        "APPDYNAMICS_CONTROLLER_SSL_ENABLED",
    }

    os_env_set = set(os.environ)

    diff_envs = required_envs.difference(os_env_set)

    if len(diff_envs) == 0:
        logging.info("AppDynamics enabled.")
        return True

    else:
        logging.info(
            "Not enabling AppDynamics as the following required variables are missing: {}.".format(
                ",".join(diff_envs)
            )
        )

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
