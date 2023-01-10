"""
For Dynatrace, metrics are directly ingested through telegraf.
No additional setup is needed.
This module only collects information for telegraf from environment variables.
"""
import logging
import os
from urllib.parse import urljoin

INGEST_ENDPOINT = "/api/v2/metrics/ingest"


def is_enabled():
    return (
        "DT_PAAS_TOKEN" in os.environ.keys()
        and "DT_SAAS_URL" in os.environ.keys()
    )


def get_ingestion_info():
    if not is_enabled():
        return None, None

    logging.info("Metrics ingestion to Dynatrace is configured")
    token = os.getenv("DT_PAAS_TOKEN")
    ingest_url = urljoin(os.getenv("DT_SAAS_URL"), INGEST_ENDPOINT)
    return token, ingest_url
