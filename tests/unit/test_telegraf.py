import os

from buildpack.telemetry import telegraf

from unittest import TestCase
from unittest.mock import patch


@patch("buildpack.telemetry.metrics.micrometer_metrics_enabled")
@patch("buildpack.telemetry.datadog.is_enabled")
class TestTelegrafIsEnabled(TestCase):
    def test_when_only_appmetrics_target_is_given(
        self, mock_datadog_is_enabled, mock_micrometer_metrics_enabled
    ):
        mock_datadog_is_enabled.return_value = False
        mock_micrometer_metrics_enabled.return_value = False
        with patch.dict(os.environ, {"APPMETRICS_TARGET": "non_empty_value"}):
            actual_state = telegraf.is_enabled("dummy_runtime")
        self.assertTrue(actual_state)

    def test_when_only_datadog_is_enabled(
        self, mock_datadog_is_enabled, mock_micrometer_metrics_enabled
    ):
        mock_datadog_is_enabled.return_value = True
        mock_micrometer_metrics_enabled.return_value = False
        self.assertTrue(telegraf.is_enabled("dummy_runtime"))

    def test_when_only_micrometer_metrics_are_enabled(
        self, mock_datadog_is_enabled, mock_micrometer_metrics_enabled
    ):
        mock_datadog_is_enabled.return_value = False
        mock_micrometer_metrics_enabled.return_value = True
        self.assertTrue(telegraf.is_enabled("dummy_runtime"))

    def test_when_nothing_is_enabled(
        self, mock_datadog_is_enabled, mock_micrometer_metrics_enabled
    ):
        mock_datadog_is_enabled.return_value = False
        mock_micrometer_metrics_enabled.return_value = False
        self.assertFalse(telegraf.is_enabled("dummy_runtime"))
