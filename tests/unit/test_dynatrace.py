import os
from unittest.mock import patch

from buildpack.telemetry import dynatrace
from unittest import TestCase

from buildpack.telemetry.dynatrace import _join_url


class TestDynatrace(TestCase):
    def test_is_enabled_false(self):
        # Should be False without necessary environment variables
        self.assertFalse(dynatrace.is_telegraf_enabled())

    def test_get_ingestion_info_for_saas(self):
        token = "DUMMY_TOKEN"
        url = "DUMMY_URL"

        env_vars = {
            "DT_PAAS_TOKEN": token,
            "DT_SAAS_URL": url,
        }

        with patch.dict(os.environ, env_vars):
            actual_info = dynatrace.get_ingestion_info()

        expected_ingest_url = _join_url(url, dynatrace.INGEST_ENDPOINT)
        expected_info = (token, expected_ingest_url)
        self.assertEqual(expected_info, actual_info)

    def test_get_ingestion_info_for_managed(self):
        token = "DUMMY_TOKEN"
        url = "DUMMY_URL"
        tenant = "DUMMY_TENANT"

        env_vars = {
            "DT_PAAS_TOKEN": token,
            "DT_SAAS_URL": url,
            "DT_TENANT": tenant,
            "DT_IS_MANAGED": "true",
        }

        with patch.dict(os.environ, env_vars):
            actual_info = dynatrace.get_ingestion_info()
        url = _join_url(url, f"e/{tenant}")
        expected_ingest_url = _join_url(url, dynatrace.INGEST_ENDPOINT)
        expected_info = (token, expected_ingest_url)
        self.assertEqual(expected_info, actual_info)

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
