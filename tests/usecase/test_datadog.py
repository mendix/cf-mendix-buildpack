import basetest
import json


class TestCaseDeployWithDatadog(basetest.BaseTest):
    def _deploy_app(self, mda_file):
        super().setUp()
        self.setUpCF(mda_file, env_vars={"DD_API_KEY": "NON-VALID-TEST-KEY"})
        self.startApp()

    def _test_datadog_running(self, mda_file):
        self._deploy_app(mda_file)
        self.assert_app_running()

        # Validate telegraf is running and has port 8125 opened for StatsD
        output = self.cmd(
            (
                "cf",
                "ssh",
                self.app_name,
                "-c",
                "lsof -i | grep '^datadog.*:8125'",
            )
        )
        assert output is not None
        assert str(output).find("datadog") >= 0

    def test_datadog_running_mx7(self):
        self._test_datadog_running("BuildpackTestApp-mx-7-16.mda")

    def test_datadog_running_mx8(self):
        self._test_datadog_running("Mendix8.1.1.58432_StarterApp.mda")

    def _test_logsubscriber_active(self, mda_file):
        self._deploy_app(mda_file)
        self.assert_app_running()

        logsubscribers_json = self.query_mxadmin(
            {"action": "get_log_settings", "params": {"sort": "subscriber"}}
        )
        self.assertIsNotNone(logsubscribers_json)

        logsubscribers = json.loads(logsubscribers_json.text)
        self.assertTrue("DataDogSubscriber" in logsubscribers["feedback"])

    def test_logsubscriber_active_mx7(self):
        self._test_logsubscriber_active("BuildpackTestApp-mx-7-16.mda")

    def test_logsubscriber_active_mx8(self):
        self._test_logsubscriber_active("Mendix8.1.1.58432_StarterApp.mda")
