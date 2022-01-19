import os

from buildpack.telemetry import metrics
from lib.m2ee.version import MXVersion

from unittest import TestCase
from unittest.mock import Mock, patch


class TestMicrometerMetrics(TestCase):
    def setUp(self) -> None:
        self.addCleanup(patch.stopall)
        patch(
            "buildpack.telemetry.metrics.get_metrics_url",
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


class TestMicrometerMetricRegistry(TestCase):
    def setUp(self) -> None:
        self.addCleanup(patch.stopall)
        patch(
            "buildpack.core.runtime.get_runtime_version",
            return_value=metrics.MXVERSION_MICROMETER,
        ).start()
        patch(
            "buildpack.telemetry.metrics.micrometer_metrics_enabled",
            return_value=True,
        ).start()

    def test_paidapps_metrics_registry(self):
        with patch.dict(os.environ, {"PROFILE": "some-random-mx-profile"}):
            result = metrics.configure_influx_registry(Mock())
            self.assertEqual(
                result.get("Metrics.Registries"),
                metrics.PAIDAPPS_METRICS_REGISTRY,
            )

    def test_freeapps_metrics_registry(self):
        with patch.dict(os.environ, {"PROFILE": "free"}):
            result = metrics.configure_influx_registry(Mock())
            self.assertEqual(
                result.get("Metrics.Registries"),
                metrics.FREEAPPS_METRICS_REGISTRY,
            )
