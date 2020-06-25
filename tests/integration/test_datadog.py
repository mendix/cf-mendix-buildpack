import json

from tests.integration import basetest


class TestCaseDeployWithDatadog(basetest.BaseTest):
    def _deploy_app(self, mda_file):
        self.stage_container(
            mda_file,
            env_vars={
                "DD_API_KEY": "NON-VALID-TEST-KEY",
                "DD_TRACE_ENABLED": "true",
            },
        )
        self.start_container()

    def _test_datadog_running(self, mda_file):
        self._deploy_app(mda_file)
        self.assert_app_running()

        # Validate Datadog is running and has expected ports open
        # Agent: 8125
        self._test_listening_on_port(8125)
        # Trace Agent: 8126
        self._test_listening_on_port(8126, "trace")
        # Mendix Logs: 9032
        self._test_listening_on_port(9032)

    def _test_listening_on_port(self, port, agent_string="agent"):
        output = self.run_on_container(
            "lsof -i | grep '^{}.*:{}'".format(agent_string, port)
        )
        assert output is not None
        assert str(output).find(agent_string) >= 0

    def _test_datadog(self, mda_file):
        self._test_datadog_running(mda_file)
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

    def test_datadog_failure_mx6(self):
        self.stage_container(
            "sample-6.2.0.mda", env_vars={"DD_API_KEY": "NON-VALID-TEST-KEY"}
        )
        self.start_container()
        self.assert_app_running()
        self.assert_string_in_recent_logs(
            "Datadog integration requires Mendix 7.14 or newer"
        )
