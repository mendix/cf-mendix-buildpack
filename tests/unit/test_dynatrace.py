import os
from unittest.mock import patch
from urllib.parse import urljoin

from buildpack.telemetry import dynatrace
from unittest import TestCase

from buildpack.telemetry.dynatrace import _join_url


class TestDynatrace(TestCase):
    def test_is_enabled_false(self):
        # Should be False without necessary environment variables
        self.assertFalse(dynatrace.is_telegraf_enabled())

    def test_get_ingestion_url(self):
        url_endpoint_combinations = [
            (
                # managed, both has slash
                "https://a-domain.nl/e/MANAGED_TENANT_ID/",
                "/api/v2/metrics/ingest",
                "https://a-domain.nl/e/MANAGED_TENANT_ID/api/v2/metrics/ingest",
            ),
            (
                # managed, only url has slash
                "https://a-domain.nl/e/MANAGED_TENANT_ID/",
                "api/v2/metrics/ingest",
                "https://a-domain.nl/e/MANAGED_TENANT_ID/api/v2/metrics/ingest",
            ),
            (
                # managed, only enpoint has slash
                "https://a-domain.nl/e/MANAGED_TENANT_ID",
                "/api/v2/metrics/ingest",
                "https://a-domain.nl/e/MANAGED_TENANT_ID/api/v2/metrics/ingest",
            ),
            (
                # managed, none has slash
                "https://a-domain.nl/e/MANAGED_TENANT_ID",
                "api/v2/metrics/ingest",
                "https://a-domain.nl/e/MANAGED_TENANT_ID/api/v2/metrics/ingest",
            ),
            (
                # saas, both has slash
                "https://SAAS_TENANT_ID.live.dynatrace.com/",
                "/api/v2/metrics/ingest",
                "https://SAAS_TENANT_ID.live.dynatrace.com/api/v2/metrics/ingest",
            ),
            (
                # saas, only url has slash
                "https://SAAS_TENANT_ID.live.dynatrace.com/",
                "api/v2/metrics/ingest",
                "https://SAAS_TENANT_ID.live.dynatrace.com/api/v2/metrics/ingest",
            ),
            (
                # saas, only endpoint has slash
                "https://SAAS_TENANT_ID.live.dynatrace.com",
                "/api/v2/metrics/ingest",
                "https://SAAS_TENANT_ID.live.dynatrace.com/api/v2/metrics/ingest",
            ),
            (
                # saas, none has slash
                "https://SAAS_TENANT_ID.live.dynatrace.com",
                "api/v2/metrics/ingest",
                "https://SAAS_TENANT_ID.live.dynatrace.com/api/v2/metrics/ingest",
            ),
        ]
        for url, endpoint, expected_ingestion_url in url_endpoint_combinations:
            with self.subTest():
                actual_ingestion_url = _join_url(url, endpoint)
                self.assertEqual(expected_ingestion_url, actual_ingestion_url)
