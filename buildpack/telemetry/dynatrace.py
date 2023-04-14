"""
For Dynatrace, we have two different ingestion methods:
1. via Dynatrace OneAgent. It's being downloaded and injected to the java
runtime.
2. via telegraf. Telegraf ingests custom runtime metrics using Dynatrace
output plugin
"""
import logging
import os
import json
from functools import lru_cache
from urllib.parse import urljoin

from buildpack import util

INGEST_ENDPOINT = "api/v2/metrics/ingest"
NAMESPACE = "dynatrace"
BUILD_PATH = os.path.join(".local", NAMESPACE)

# Environment variables for Dynatrace OneAgent
# Only passed to the agent if set as environment variable
default_env = {
    # -- Environment variables for the integration
    # "DT_PAAS_TOKEN": required, also used for telegraf integration
    # "DT_SAAS_URL": required, also used for telegraf integration
    "DT_TENANT": None,  # required for agent integration, dynatrace envID
    # optional, default value is get from manifest.json which is downloaded
    # along with the agent installer
    "DT_TENANTTOKEN": None,
    # -- Environment variables for orchestration
    "DT_CLUSTER_ID": None,  # optional, default not set
    # optional metadata e.g. Department=Acceptance Stage=Sprint
    "DT_CUSTOM_PROP": None,
    # -- Environment variables for troubleshooting
    "DT_LOGSTREAM": "stdout",  # optional
    # Use this environment variable to define the console log level.
    # Valid options are: NONE, SEVERE, and INFO.
    "DT_LOGLEVELCON": None,
    # Set to true or false to enable or disable OneAgent.
    "DT_AGENTACTIVE": None,
}


def stage(buildpack_dir, root_dir, cache_path):
    """
    Downloads and unzips necessary OneAgent components
    """
    if is_agent_enabled():
        try:
            util.resolve_dependency(
                dependency="dynatrace.agent",
                destination=os.path.join(root_dir, NAMESPACE),
                buildpack_dir=buildpack_dir,
                cache_dir=cache_path,  # CACHE_DIR,
                unpack=True,
                overrides={
                    # need to us rstrip because otherwise the download link
                    # formed with double slashes and it doesn't work
                    "url": os.environ.get("DT_SAAS_URL").rstrip("/"),
                    "environment": os.environ.get("DT_TENANT"),
                    "token": os.environ.get("DT_PAAS_TOKEN"),
                },
                # cache is not working properly, so ignoring for now.
                # Can be debugged later, a stack trace exists in the PR:
                # https://github.com/mendix/cf-mendix-buildpack/pull/562
                ignore_cache=True,
            )
        except Exception:
            logging.warning("Dynatrace agent download and unpack failed", exc_info=True)


def update_config(m2ee):
    """
    Injects Dynatrace configuration to java runtime
    """
    if not is_agent_enabled():
        logging.debug(
            "Skipping Dynatrace OneAgent setup, required env vars are not set"
        )
        return

    logging.info("Enabling Dynatrace OneAgent")
    try:
        manifest = get_manifest()
    except Exception:
        logging.warning("Failed to parse Dynatrace manifest file", exc_info=True)
        return

    agent_path = get_agent_path()
    logging.debug("Agent path: [%s]", agent_path)
    if not os.path.exists(agent_path):
        raise Exception(f"Dynatrace Agent not found: {agent_path}")

    # dynamic default
    default_env.update({"DT_TENANTTOKEN": manifest.get("tenantToken")})

    for key, dv in default_env.items():
        value = os.environ.get(key, dv)
        if value is not None:
            util.upsert_custom_environment_variable(m2ee, key, value)
    util.upsert_custom_environment_variable(
        m2ee, "DT_CONNECTION_POINT", get_connection_endpoint()
    )

    util.upsert_javaopts(
        m2ee,
        [
            f"-agentpath:{os.path.abspath(agent_path)}",
            "-Xshare:off",
        ],
    )


@lru_cache(maxsize=None)
def get_manifest():
    manifest_path = os.path.join(BUILD_PATH, "manifest.json")
    with open(manifest_path, "r") as file_handler:
        return json.load(file_handler)


def get_connection_endpoint():
    manifest = get_manifest()
    endpoints = manifest.get("communicationEndpoints", [])
    # prepend the DT_SAAS_URL because the communication endpoints might not be correct
    endpoints.insert(0, _join_url(os.environ.get("DT_SAAS_URL"), "communication"))
    return ";".join(endpoints)


def get_agent_path():
    manifest = get_manifest()
    technologies = manifest.get("technologies")
    java_binaries = technologies.get("java").get("linux-x86-64")
    for file in java_binaries:
        binary_type = file.get("binarytype")
        if binary_type == "loader":
            return os.path.join(BUILD_PATH, file.get("path"))


def is_telegraf_enabled():
    return "DT_PAAS_TOKEN" in os.environ.keys() and "DT_SAAS_URL" in os.environ.keys()


def is_agent_enabled():
    return is_telegraf_enabled() and ("DT_TENANT" in os.environ.keys())


def get_ingestion_info():
    if not is_telegraf_enabled():
        return None, None

    logging.info("Metrics ingestion to Dynatrace via telegraf is configured")
    token = os.getenv("DT_PAAS_TOKEN")
    base_url = os.getenv("DT_SAAS_URL")
    tenant_id = os.getenv("DT_TENANT")
    if os.getenv("DT_IS_MANAGED", "false").lower() == "true":
        base_url = _join_url(base_url, f"e/{tenant_id}")
    ingest_url = _join_url(base_url, INGEST_ENDPOINT)
    return token, ingest_url


def _join_url(saas_url, endpoint):
    """
    Basic url join but purposefully isolated to add some unittests easily.
    When merging an url and an additional endpoint, python's urljoin method
    has so many little details. See:
    https://stackoverflow.com/questions/10893374/python-confusions-with-urljoin

    So, basically we need to make sure that the url ends with '/' and
    the endpoint does not start with '/'
    """

    saas_url = f"{saas_url}/"
    endpoint = endpoint.lstrip("/")
    return urljoin(saas_url, endpoint)
