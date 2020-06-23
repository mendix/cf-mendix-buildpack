import copy
from unittest import TestCase
from unittest.mock import Mock

from buildpack.runtime_components.metrics import (
    FreeAppsMetricsEmitterThread,
    PaidAppsMetricsEmitterThread,
)


class TestNegativeMemoryMetricsThrowError(TestCase):
    def test_validating_bad_metrics(self):
        m2ee_stats = {"memory": {"javaheap": -12345}}
        with self.assertRaises(RuntimeError):
            PaidAppsMetricsEmitterThread._sanity_check_m2ee_stats(m2ee_stats)

    def test_no_memorypools_good_metrics(self):
        m2ee_stats = {"memory": {"javaheap": 12345}}
        self.assertIsNone(
            PaidAppsMetricsEmitterThread._sanity_check_m2ee_stats(m2ee_stats)
        )

    def test_non_ints_dont_cause_problems(self):
        m2ee_stats = {
            "memory": {
                "javaheap": 123,
                "memorypools": {"blah": "stuff"},
                "foo": "bar",
            }
        }
        self.assertIsNone(
            PaidAppsMetricsEmitterThread._sanity_check_m2ee_stats(m2ee_stats)
        )

    def test_non_ints_dont_cause_problems_when_raising(self):
        m2ee_stats = {
            "memory": {
                "javaheap": -123,
                "memorypools": {"blah": "stuff"},
                "foo": "bar",
            }
        }
        with self.assertRaises(RuntimeError):
            PaidAppsMetricsEmitterThread._sanity_check_m2ee_stats(m2ee_stats)

    def test_underlying_log_message_propagates_upwards(self):
        m2ee = Mock()
        m2ee_stats = {
            "memory": {
                "javaheap": -123,
                "memorypools": {"blah": "stuff"},
                "foo": "bar",
            }
        }
        interval = 1
        metrics_emitter = PaidAppsMetricsEmitterThread(interval, m2ee)

        with self.assertRaises(RuntimeError):
            # ensure we log the error, before we raise the exception
            with self.assertLogs(level="ERROR") as cm:
                metrics_emitter._sanity_check_m2ee_stats(m2ee_stats)

        # check the output logs contain the following message
        self.assertIn("Memory stats with non-logical values", cm.output[-1])


class TestFreeAppsMetricsEmitter(TestCase):
    def setUp(self):
        self.mock_user_session_metrics = {
            "sessions": {
                "named_users": 0,
                "anonymous_sessions": 0,
                "named_user_sessions": 0,
                "user_sessions": {},
            }
        }
        interval = 10
        m2ee = Mock()

        self.metrics_emitter = FreeAppsMetricsEmitterThread(interval, m2ee)
        self.metrics_emitter._get_munin_stats = Mock(
            return_value=copy.deepcopy(self.mock_user_session_metrics)
        )
        self.metrics_emitter.emit = Mock()
        self.metrics_emitter.setDaemon(True)

    def test_inject_user_session_metrics(self):
        stats = {"key": "value"}
        expected_stats = copy.deepcopy(stats)
        expected_stats["mendix_runtime"] = self.mock_user_session_metrics

        stats = self.metrics_emitter._inject_user_session_metrics(stats)
        self.assertTrue(self.metrics_emitter._get_munin_stats.called)
        self.assertEqual(expected_stats, stats)

    def test_inject_user_session_metrics_when_mendix_runtime_metrics_already_present(
        self,
    ):
        stats = {
            "key": "value",
            "mendix_runtime": {"other_key": "other_value"},
        }
        expected_stats = copy.deepcopy(stats)
        expected_stats["mendix_runtime"].update(self.mock_user_session_metrics)

        stats = self.metrics_emitter._inject_user_session_metrics(stats)
        self.assertTrue(self.metrics_emitter._get_munin_stats.called)
        self.assertEqual(expected_stats, stats)

    def test_inject_user_session_metrics_when_exception_raised(self):
        stats = {"key": "value"}
        expected_stats = copy.deepcopy(stats)
        expected_stats["mendix_runtime"] = {"sessions": {}}

        self.metrics_emitter._get_munin_stats = Mock(
            side_effect=Exception("M2EE Exception!")
        )
        stats = self.metrics_emitter._inject_user_session_metrics(stats)
        self.assertTrue(self.metrics_emitter._get_munin_stats.called)
        self.assertEqual(stats, expected_stats)
