import os

from buildpack import util
from lib.m2ee import logger


def compile(destination_path, cache_path):
    if appdynamics_used():
        util.download_and_unpack(
            util.get_blobstore_url(
                "/mx-buildpack/appdynamics-agent-4.3.5.7.tar.gz"
            ),
            destination_path,  # DOT_LOCAL_LOCATION,
            cache_path,  # CACHE_DIR,
        )


def update_config(m2ee, app_name):
    if not appdynamics_used():
        return
    logger.info("Adding app dynamics")
    m2ee.config._conf["m2ee"]["javaopts"].append(
        "-javaagent:{path}".format(
            path=os.path.abspath(".local/ver4.3.5.7/javaagent.jar")
        )
    )
    m2ee.config._conf["m2ee"]["javaopts"].append(
        "-Dappagent.install.dir={path}".format(
            path=os.path.abspath(".local/ver4.3.5.7")
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
