from buildpack.telemetry.appdynamics_telegraf_output import (
    convert_and_push_payload,
    APPDYNAMICS_MACHINE_AGENT_URL,
    METRIC_TREE_BASE_NODE,
)
from unittest import TestCase
from unittest.mock import patch
import requests_mock
import json


METRICS = {
    "metrics": [
        {
            "fields": {"value": 10737418240},
            "name": "test_name",
            "tags": {
                "host": "nonprod4denis-test.dev.mendixcloud.com-0",
                "db": "test_db",
            },
            "timestamp": 1647939590,
        }
    ]
}


class TestConvertPayload(TestCase):
    @patch("builtins.input", return_value=json.dumps(METRICS))
    def test_convert_and_push_payload(self, mock_input):

        with requests_mock.Mocker() as m:
            m.post(APPDYNAMICS_MACHINE_AGENT_URL)
            convert_and_push_payload()
            last_request_json = m.last_request.json()

            self.assertEqual(
                last_request_json[0]["metricName"],
                "|".join(
                    (METRIC_TREE_BASE_NODE, "test_name|Database 'test_db'")
                ),
            )
