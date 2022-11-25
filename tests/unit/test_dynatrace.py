import os
from unittest.mock import patch
from urllib.parse import urljoin

from buildpack.telemetry import dynatrace
from unittest import TestCase


class TestDynatrace(TestCase):
    def test_is_enabled_false(self):
        # Should be False without necessary environment variables
        self.assertFalse(dynatrace.is_enabled())

    def test_get_ingestion_info(self):
        # for get_ingestion_info(), also covers enabled case of is_enabled()
        token = "DUMMY_TOKEN"
        url = "DUMMY_URL"
        expected_ingest_url = urljoin(url, dynatrace.INGEST_ENDPOINT)
        env_vars = {"DT_PAAS_TOKEN": token, "DT_SAAS_URL": url}
        with patch.dict(os.environ, env_vars):
            actual_info = dynatrace.get_ingestion_info()

        expected_info = (token, expected_ingest_url)
        self.assertEqual(expected_info, actual_info)
