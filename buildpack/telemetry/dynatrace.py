"""
For Dynatrace, metrics are directly ingested through telegraf.
No additional setup is needed.
This module only collects information for telegraf from environment variables.
"""
import logging
import os
import json
from urllib.parse import urljoin

INGEST_ENDPOINT = "api/v2/metrics/ingest"


from buildpack import util
# Environment variables for Dynatrace OneAgent
# Only passed to the agent if set as environment variable
default_env = {
    # -- Environment variables for the integration
    # "DT_PAAS_TOKEN": required, also used for telegraf integration
    # "DT_SAAS_URL": required, also used for telegraf integration
    "DT_TENANT": None,  # required for agent integration, dynatrace environment ID
    "DT_TENANTTOKEN": None,  # optional, default value is get from manifest.json which is downloaded along with the agent installer
    # -- Environment variables for orchestration
    "DT_LOCALTOVIRTUALHOSTNAME": None,  # optional, default not set
    "DT_APPLICATIONID": None,  # optional, default not set
    "DT_NODE_ID": None,  # optional, default not set
    "DT_CLUSTER_ID": None,  # optional, default not set
    "DT_TAGS": None,  # optional tags e.g. MikesStuff easyTravel=Mike
    "DT_CUSTOM_PROP": None,  # optional metadata e.g. Department=Acceptance Stage=Sprint
    # -- Environment variables for troubleshooting
    "DT_LOGSTREAM": "stdout",  # optional
    "DT_LOGLEVELCON": None,  # Use this environment variable to define the console log level. Valid options are: NONE, SEVERE, and INFO.
    "DT_AGENTACTIVE": None,  # Set to true or false to enable or disable OneAgent.
    # -- Networking environment variables
    "DT_NETWORK_ZONE": None,  # optional, Specifies to use a network zone. For more information
    "DT_PROXY": None, # Optional, When using a proxy, use this environment variable to pass proxy credentials.
}


def stage(buildpack_dir, build_path, cache_path):
    """
    Downloads and unzips necessary OneAgent components
    """
    if is_agent_enabled():
        try:
            util.resolve_dependency(
                "dynatrace.agent",
                build_path,  # DOT_LOCAL_LOCATION,
                buildpack_dir=buildpack_dir,
                cache_dir=cache_path,  # CACHE_DIR,
                unpack=True,
                overrides={
                    "url": os.environ.get("DT_SAAS_URL"),
                    "environment": os.environ.get("DT_TENANT"),
                    "token": os.environ.get("DT_PAAS_TOKEN"),
                },
                ignore_cache=True
            )
        except Exception as e:
            logging.warning(
                "Dynatrace agent download and unpack failed", exc_info=True
            )


def update_config(m2ee, app_name):
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
    except Exception as e:
        logging.warning(
            "Failed to parse Dynatrace manifest file", exc_info=True
        )
        return

    # dynamic default
    default_env.update({"DT_TENANTTOKEN": manifest.get("tenantToken")})

    for key, dv in default_env.items():
        value = os.environ.get(key, dv)
        if value:
            util.upsert_custom_environment_variable(m2ee, key, value)
    util.upsert_custom_environment_variable(
        m2ee, "DT_CONNECTION_POINT", get_connection_endpoint()
    )

    agent_path = os.path.join(".local", get_agent_path())
    if not os.path.exists(agent_path):
        raise Exception(
            "Dynatrace Agent not found: {agent_path}".format(agent_path)
        )

    util.upsert_javaopts(
        m2ee,
        [
            "-agentpath:{path}".format(path=os.path.abspath(agent_path)),
            "-Xshare:off",
        ],
    )


def get_manifest():
    with open(".local/manifest.json", "r") as f:
        return json.load(f)


def get_connection_endpoint():
    manifest = get_manifest()
    endpoints = manifest.get("communicationEndpoints", [])
    # prepend the DT_SAAS_URL because the communication endpoints might not be correct
    endpoints.insert(
        0, "{url}/communication".format(url=os.environ.get("DT_SAAS_URL"))
    )
    return ";".join(endpoints)


def get_agent_path():
    manifest = get_manifest()
    technologies = manifest.get("technologies")
    java_binaries = technologies.get("java").get("linux-x86-64")
    for f in java_binaries:
        binary_type = f.get("binarytype")
        if binary_type == "loader":
            return f.get("path")


def is_telegraf_enabled():
    return (
        "DT_PAAS_TOKEN" in os.environ.keys()
        and "DT_SAAS_URL" in os.environ.keys()
    )


def is_agent_enabled():
    return is_telegraf_enabled() and ("DT_TENANT" in os.environ.keys())


def get_ingestion_info():
    if not is_telegraf_enabled():
        return None, None

    logging.info("Metrics ingestion to Dynatrace via telegraf is configured")
    token = os.getenv("DT_PAAS_TOKEN")
    ingest_url = _get_ingestion_url(os.getenv("DT_SAAS_URL"), INGEST_ENDPOINT)
    return token, ingest_url


def _get_ingestion_url(saas_url, endpoint):
    """
    Basic url join but purposefully isolated to add some unittests easily.
    When merging an url and an additional endpoint, python's urljoin method
    has so many little details. See:
    https://stackoverflow.com/questions/10893374/python-confusions-with-urljoin

    So, basically we need to make sure that the url ends with '/' and
    the endpoint does not start with '/'
    """

    saas_url = f"{saas_url}/"
    if endpoint.startswith('/'):
        endpoint = endpoint[1:]
    return urljoin(saas_url, endpoint)
