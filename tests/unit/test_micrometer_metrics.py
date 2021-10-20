import os

from buildpack.runtime_components import metrics

from unittest import TestCase
from unittest.mock import patch


class TestMicrometerMetrics(TestCase):
    def setUp(self) -> None:
        self.addCleanup(patch.stopall)
        patch(
            "buildpack.runtime_components.metrics.get_metrics_url",
            return_value="non_empty_url",
        ).start()

    def test_old_runtime_forced_to_disable(self):
        with patch.dict(os.environ, {"DISABLE_MICROMETER_METRICS": "true"}):
            actual_state = metrics.micrometer_metrics_enabled("9.0.0")
        self.assertFalse(actual_state)

    def test_old_runtime_not_forced_to_disable(self):
        with patch.dict(os.environ, {"DISABLE_MICROMETER_METRICS": "false"}):
            actual_state = metrics.micrometer_metrics_enabled("9.0.0")
        self.assertFalse(actual_state)

    def test_new_runtime_forced_to_disable(self):
        with patch.dict(os.environ, {"DISABLE_MICROMETER_METRICS": "true"}):
            actual_state = metrics.micrometer_metrics_enabled("9.7.0")
        self.assertFalse(actual_state)

    def test_new_runtime_not_forced_to_disable(self):
        with patch.dict(os.environ, {"DISABLE_MICROMETER_METRICS": "false"}):
            actual_state = metrics.micrometer_metrics_enabled("9.7.0")
        self.assertTrue(actual_state)
