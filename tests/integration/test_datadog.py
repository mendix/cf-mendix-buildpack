import json
import os

from buildpack import datadog
from tests.integration import basetest


class TestCaseDeployWithDatadog(basetest.BaseTestWithPostgreSQL):
    def _deploy_app(self, mda_file):
        self.stage_container(
            mda_file,
            env_vars={
                "DD_API_KEY": os.environ.get(
                    "DD_API_KEY", "NON-VALID-TEST-KEY"
                ),
                "DD_TRACE_ENABLED": "true",
                # "DD_TRACE_DEBUG": "true",
                "DATADOG_DATABASE_DISKSTORAGE_METRIC": "true",
                "DATABASE_DISKSTORAGE": 10.0,
                "DATADOG_DATABASE_RATE_COUNT_METRICS": "true",
                "TAGS": json.dumps(["app:testapp", "env:dev"]),
            },
        )
        self.start_container()

    def _test_datadog_running(self, mda_file):
        self._deploy_app(mda_file)
        self.assert_app_running()

        # Validate Telegraf and Datadog are running and have expected ports open
        # Telegraf
        self.assert_running("telegraf")
        self.assert_string_not_in_recent_logs(
            "E! [inputs.postgresql_extensible]"
        )
        # Agent: 18125
        self.assert_listening_on_port(datadog.get_statsd_port(), "agent")
        # Trace Agent: 8126
        self.assert_listening_on_port(8126, "trace")
        # Mendix Logs: 9032
        self.assert_listening_on_port(datadog.LOGS_PORT, "agent")

    def _test_dd_tags(self):
        self.assert_string_in_recent_logs(
            "'DD_TAGS': 'app:testapp,env:dev,service:testapp'"
        )

    def _test_datadog(self, mda_file):
        self._test_datadog_running(mda_file)
        self._test_dd_tags()
        self._test_logsubscriber_active()

    def _test_logsubscriber_active(self):
        self.assert_string_in_recent_logs(
            "Datadog Agent log subscriber is ready"
        )

        logsubscribers_json = self.query_mxadmin(
            {"action": "get_log_settings", "params": {"sort": "subscriber"}}
        )
        self.assertIsNotNone(logsubscribers_json)

        logsubscribers = json.loads(logsubscribers_json.text)
        self.assertTrue("DatadogSubscriber" in logsubscribers["feedback"])

    def test_datadog_mx7(self):
        self._test_datadog("BuildpackTestApp-mx-7-16.mda")

    def test_datadog_mx8(self):
        self._test_datadog("Mendix8.1.1.58432_StarterApp.mda")
