import os
from operator import itemgetter

from buildpack.telemetry import metrics

from unittest import TestCase
from unittest.mock import Mock, patch
from parameterized import parameterized


class TestMicrometerMetrics(TestCase):
    def setUp(self) -> None:
        self.addCleanup(patch.stopall)
        patch(
            "buildpack.telemetry.metrics.get_metrics_url",
            return_value="non_empty_url",
        ).start()

    @parameterized.expand(
        [
            ["false", "dummy_forwarder_url", "non_empty_url"],
            ["false", "", "non_empty_url"],
            ["true", "", "non_empty_url"],
            ["true", "dummy_forwarder_url", "dummy_forwarder_url"],
        ]
    )
    def test_get_micrometer_metrics_url(
        self,
        use_trends_forwarder,
        trends_forwarder_url,
        expected_url,
    ):
        with patch.dict(
            os.environ,
            {
                "USE_TRENDS_FORWARDER": use_trends_forwarder,
                "TRENDS_FORWARDER_URL": trends_forwarder_url,
            },
        ):

            url = metrics.get_micrometer_metrics_url()
            self.assertEqual(url, expected_url)

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

    @patch("buildpack.telemetry.datadog.is_enabled", return_value=False)
    def test_paidapps_metrics_registry(self, is_enabled):
        with patch.dict(os.environ, {"PROFILE": "some-random-mx-profile"}):
            result = metrics.configure_metrics_registry(Mock())
            self.assertEqual(
                result[0]["type"],
                "influx",
            )

    @patch("buildpack.telemetry.datadog.is_enabled", return_value=True)
    def test_paidapps_metrics_registry_statsd(self, is_enabled):
        with patch.dict(os.environ, {"PROFILE": "some-random-mx-profile"}):
            result = metrics.configure_metrics_registry(Mock())
            metrics_registries = sorted(result, key=itemgetter("type"))
            self.assertEqual(
                metrics_registries[0]["type"],
                "influx",
            )
            self.assertEqual(
                metrics_registries[1]["type"],
                "statsd",
            )

    def test_freeapps_metrics_registry(self):
        with patch.dict(os.environ, {"PROFILE": "free"}):
            result = metrics.configure_metrics_registry(Mock())
            self.assertEqual(
                result,
                metrics.FREEAPPS_METRICS_REGISTRY,
            )


class TestOldApps(TestCase):
    @patch("buildpack.core.runtime.get_runtime_version", return_value="9.6.0")
    @patch("buildpack.telemetry.datadog.is_enabled", return_value=True)
    def test_paidapps_less_than_9_7(self, dd_is_enabled, mocked_runtime_version):
        with patch.dict(os.environ, {"PROFILE": "some-random-mx-profile"}):
            result = metrics.configure_metrics_registry(Mock())
            # nothing to configure for apps below 9.7.0
            assert result == []
