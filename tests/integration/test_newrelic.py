from tests.integration import basetest


class TestCaseDeployWithNewRelic(basetest.BaseTest):
    def _deploy_app(self, mda_file, newrelic=True):
        super().setUp()

        env_vars = {}
        if newrelic:
            env_vars["NEW_RELIC_LICENSE_KEY"] = "dummy_token"
            env_vars["NEW_RELIC_METRICS_URI"] = "https://metric-api.eu.newrelic.com/metric/v1"
            env_vars["NEW_RELIC_LOGS_URI"] = "https://log-api.eu.newrelic.com/log/v1"

        self.stage_container(mda_file, env_vars=env_vars)
        self.start_container()

    def _test_newrelic_running(self, mda_file):
        self._deploy_app(mda_file)
        self.assert_app_running()

        # Check if FluentBit is running
        output = self.run_on_container("ps -ef | grep fluentbit")
        assert output is not None
        assert str(output).find("fluent-bit") >= 0

        # Check if Telegraf is running
        self.assert_running("telegraf")

        # Check if New Relic is running
        output = self.run_on_container("ps -ef | grep newrelic")
        assert str(output).find("newrelic.jar") >= 0

    def _test_newrelic_not_running(self, mda_file):
        self._deploy_app(mda_file, newrelic=False)
        self.assert_app_running()

        # Check if FluentBit is not running
        output = self.run_on_container("ps -ef | grep fluentbit")
        assert str(output).find("fluent-bit") == -1

        # Check if New Relic is not running
        output = self.run_on_container("ps -ef | grep newrelic")
        assert str(output).find("newrelic.jar") == -1

    def _test_newrelic_is_configured(self):
        self.assert_string_in_recent_logs(
            "New Relic has been configured successfully."
        )

    def _test_newrelic_is_not_configured(self):
        self.assert_string_in_recent_logs("Skipping New Relic setup")

    def test_newrelic_mx9(self):
        self._test_newrelic_running("BuildpackTestApp-mx9-18.mda")
        self._test_newrelic_is_configured()

    def test_newrelic_not_configured(self):
        self._test_newrelic_not_running("BuildpackTestApp-mx9-18.mda")
        self._test_newrelic_is_not_configured()
