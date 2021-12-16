import logging
import os

from buildpack import util

APPDYNAMICS_VERSION = "21.11.1.33280"


def stage(buildpack_dir, destination_path, cache_path):
    if appdynamics_used():
        util.resolve_dependency(
            util.get_blobstore_url(
                "/mx-buildpack/appdynamics/appdynamics-agent-1.8-{}.zip".format(
                    APPDYNAMICS_VERSION + "-mendix"
                )
            ),
            destination_path,  # DOT_LOCAL_LOCATION,
            buildpack_dir=buildpack_dir,
            cache_dir=cache_path,  # CACHE_DIR,
        )


def update_config(m2ee, app_name):
    if not appdynamics_used():
        return
    logging.info("Adding app dynamics")
    util.upsert_javaopts(
        m2ee,
        [
            "-javaagent:{path}".format(
                path=os.path.abspath(
                    ".local/ver" + APPDYNAMICS_VERSION + "/javaagent.jar"
                )
            ),
            "-Dappagent.install.dir={path}".format(
                path=os.path.abspath(".local/ver" + APPDYNAMICS_VERSION)
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


def appdynamics_used():
    for key, _ in os.environ.items():
        if key.startswith("APPDYNAMICS_"):
            return True
    return False
