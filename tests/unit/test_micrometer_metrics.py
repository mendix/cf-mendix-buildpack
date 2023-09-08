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
    def _get_registry_filters(self, registry, registry_type, deny=False):
        """
        Returns filters set on the registry entries by type.
        Defaults to the allow list of filters.
        """

        values = list()
        entries = [entry for entry in registry if entry.get("type") == registry_type]
        for entry in entries:
            for filter_entry in entry.get("filters"):
                if not deny:
                    # just fetch the allowed ones
                    if filter_entry["result"] == "accept":
                        values.extend(filter_entry["values"])
                else:
                    # just add the deny ones
                    if filter_entry["result"] == "deny":
                        values.extend(filter_entry["values"])

        return values

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
            # Ensure we have a statsd entry
            self.assertTrue(
                [
                    entry
                    for entry in metrics_registries
                    if entry.get("type") == "statsd"
                ]
            )

    @patch("buildpack.telemetry.datadog.is_enabled", return_value=True)
    def test_apm_metrics_filters_in_registries(self, is_enabled):
        with patch.dict(
            os.environ,
            {
                "PROFILE": "some-random-mx-profile",
                "APM_METRICS_FILTER_ALLOW": "allowed_metric",
                "APM_METRICS_FILTER_DENY": "denied_metric",
            },
        ):
            result = metrics.configure_metrics_registry(Mock())
            metrics_registries = sorted(result, key=itemgetter("type"))

            # influx registry shouldn't have the filters
            self.assertNotIn(
                "allowed_metric",
                self._get_registry_filters(metrics_registries, "influx"),
            )

            self.assertNotIn(
                "denied_metric",
                self._get_registry_filters(metrics_registries, "influx", True),
            )

            # statsd registry should have the filters
            self.assertIn(
                "allowed_metric",
                self._get_registry_filters(metrics_registries, "statsd"),
            )

            self.assertIn(
                "denied_metric",
                self._get_registry_filters(metrics_registries, "statsd", True),
            )

    @patch("buildpack.telemetry.datadog.is_enabled", return_value=True)
    def test_statsd_registry_when_only_allow_filter_is_provided(self, is_enabled):
        with patch.dict(
            os.environ,
            {
                "PROFILE": "some-random-mx-profile",
                "APM_METRICS_FILTER_ALLOW": "allowed_metric",
            },
        ):
            result = metrics.configure_metrics_registry(Mock())
            metrics_registries = sorted(result, key=itemgetter("type"))

            # Allow list should contain allowed_metric
            self.assertIn(
                "allowed_metric",
                self._get_registry_filters(metrics_registries, "statsd"),
            )

            # Deny list should be empty to deny all other metrics
            self.assertEqual(
                [""], self._get_registry_filters(metrics_registries, "statsd", True)
            )

    @patch("buildpack.telemetry.datadog.is_enabled", return_value=True)
    def test_statsd_registry_when_only_deny_filter_is_provided(self, is_enabled):
        with patch.dict(
            os.environ,
            {
                "PROFILE": "some-random-mx-profile",
                "APM_METRICS_FILTER_DENY": "denied_metric",
            },
        ):
            result = metrics.configure_metrics_registry(Mock())
            metrics_registries = sorted(result, key=itemgetter("type"))

            # Allow list should be empty list
            self.assertEqual(
                [], self._get_registry_filters(metrics_registries, "statsd")
            )

            # Deny list should contain denied_metric
            self.assertIn(
                "denied_metric",
                self._get_registry_filters(metrics_registries, "statsd", True),
            )

    @patch("buildpack.telemetry.datadog.is_enabled", return_value=True)
    def test_statsd_registry_when_no_filter_is_provided(self, is_enabled):
        with patch.dict(
            os.environ,
            {
                "PROFILE": "some-random-mx-profile",
            },
        ):
            result = metrics.configure_metrics_registry(Mock())
            metrics_registries = sorted(result, key=itemgetter("type"))

            # Allow list should be empty list
            self.assertEqual(
                [], self._get_registry_filters(metrics_registries, "statsd")
            )

            # Deny list should contain denied_metric
            self.assertEqual(
                [], self._get_registry_filters(metrics_registries, "statsd", True)
            )

    @patch("buildpack.telemetry.datadog.is_enabled", return_value=True)
    def test_statsd_registry_when_deny_all_is_set(self, is_enabled):
        with patch.dict(
            os.environ,
            {
                "PROFILE": "some-random-mx-profile",
                "APM_METRICS_FILTER_ALLOW": "allowed_metric",
                "APM_METRICS_FILTER_DENY": "denied_metric",
                "APM_METRICS_FILTER_DENY_ALL": "true",
            },
        ):
            result = metrics.configure_metrics_registry(Mock())
            metrics_registries = sorted(result, key=itemgetter("type"))

            # statsd registry should be configured to deny everything
            self.assertEqual(
                [], self._get_registry_filters(metrics_registries, "statsd")
            )

            self.assertEqual(
                [""], self._get_registry_filters(metrics_registries, "statsd", True)
            )

    def test_freeapps_metrics_registry(self):
        with patch.dict(os.environ, {"PROFILE": "free"}):
            result = metrics.configure_metrics_registry(Mock())
            self.assertEqual(
                result,
                [metrics.get_freeapps_registry()],
            )


class TestOldApps(TestCase):
    @patch("buildpack.core.runtime.get_runtime_version", return_value="9.6.0")
    @patch("buildpack.telemetry.datadog.is_enabled", return_value=True)
    def test_paidapps_less_than_9_7(self, dd_is_enabled, mocked_runtime_version):
        with patch.dict(os.environ, {"PROFILE": "some-random-mx-profile"}):
            result = metrics.configure_metrics_registry(Mock())
            # nothing to configure for apps below 9.7.0
            assert result == []


class TestAPMMetricsFilterSanitization(TestCase):
    @parameterized.expand(
        [
            [
                "metric_1,metric_2",
                ["metric_1", "metric_2"],
            ],
            [
                "metric_1, metric_2",
                ["metric_1", "metric_2"],
            ],
            [
                "metric_1, metric_2,",
                ["metric_1", "metric_2"],
            ],
            [
                "metric_1,metric_2 ",
                ["metric_1", "metric_2"],
            ],
            [
                " metric_1,metric_2",
                ["metric_1", "metric_2"],
            ],
            [
                "",
                [""],
            ],
        ]
    )
    def test_sanitize_metrics_filter(self, input_string, expected_list):
        actual_list = metrics.sanitize_metrics_filter(input_string)
        self.assertEqual(expected_list, actual_list)
