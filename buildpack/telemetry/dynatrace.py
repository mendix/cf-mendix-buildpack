"""
For Dynatrace, metrics are directly ingested through telegraf.
No additional setup is needed.
This module only collects information for telegraf from environment variables.
"""
import logging
import os
import json
from urllib.parse import urljoin

INGEST_ENDPOINT = "/api/v2/metrics/ingest"


from buildpack import util
'''
TODO: If agent works without them, try removing unused env vars 
to prevent confusion. 
'''
default_env = {
    "DT_TENANTTOKEN": None,  # optional, default to one found in manifest.json
    "DT_APPLICATIONID": None,  # optional, default not set
    "DT_TENANT": None,  # required, environment ID (uuid format)
    # "DT_PAAS_TOKEN": None,  # required
    # "DT_SAAS_URL": None,  # required
    "DT_LOGSTREAM": "stdout",
    "DT_NETWORK_ZONE": None,  # optional, not sure what this means :D
    "DT_CUSTOM_PROP": None,  # optional metadata e.g. Department=Acceptance Stage=Sprint
    "DT_TAGS": None,  # optional tags e.g. MikesStuff easyTravel=Mike
}


def stage(buildpack_dir, build_path, cache_path):
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
    ingest_url = urljoin(os.getenv("DT_SAAS_URL"), INGEST_ENDPOINT)
    return token, ingest_url
