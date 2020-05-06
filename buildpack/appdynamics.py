import logging
import os

from buildpack import util

APPDYNAMICS_VERSION = "20.3.0.29587"


def compile(destination_path, cache_path):
    if appdynamics_used():
        util.download_and_unpack(
            util.get_blobstore_url(
                "/mx-buildpack/appdynamics-agent-{}.zip".format(
                    APPDYNAMICS_VERSION
                )
            ),
            destination_path,  # DOT_LOCAL_LOCATION,
            cache_path,  # CACHE_DIR,
        )


def update_config(m2ee, app_name):
    if not appdynamics_used():
        return
    logging.info("Adding app dynamics")
    m2ee.config._conf["m2ee"]["javaopts"].append(
        "-javaagent:{path}".format(
            path=os.path.abspath(
                ".local/ver" + APPDYNAMICS_VERSION + "/javaagent.jar"
            )
        )
    )
    m2ee.config._conf["m2ee"]["javaopts"].append(
        "-Dappagent.install.dir={path}".format(
            path=os.path.abspath(".local/ver" + APPDYNAMICS_VERSION)
        )
    )
    APPDYNAMICS_AGENT_NODE_NAME = "APPDYNAMICS_AGENT_NODE_NAME"
    if os.getenv(APPDYNAMICS_AGENT_NODE_NAME):
        m2ee.config._conf["m2ee"]["custom_environment"][
            APPDYNAMICS_AGENT_NODE_NAME
        ] = (
            "%s-%s"
            % (
                os.getenv(APPDYNAMICS_AGENT_NODE_NAME),
                os.getenv("CF_INSTANCE_INDEX", "0"),
            )
        )


def appdynamics_used():
    for key, _ in os.environ.items():
        if key.startswith("APPDYNAMICS_"):
            return True
    return False
