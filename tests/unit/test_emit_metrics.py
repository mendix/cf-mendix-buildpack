import copy
from unittest import TestCase
from unittest.mock import Mock

from buildpack.runtime_components.metrics import FreeAppsMetricsEmitterThread


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
