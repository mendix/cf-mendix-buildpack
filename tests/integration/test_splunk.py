from tests.integration import basetest


SPLUNK_LOGS_PATTERN = r"([S,s]plunk)|([F,f]luent\s*[B,b]it)"


class TestCaseDeployWithSplunk(basetest.BaseTest):
    def _deploy_app(self, mda_file, splunk=True):
        super().setUp()

        env_vars = {
            "SPLUNK_HOST": "test.test.com",
        }

        if splunk:
            env_vars["SPLUNK_TOKEN"] = "dummy_token"

        self.stage_container(mda_file, env_vars=env_vars)
        self.start_container()

    def _test_fluentbit_running(self, mda_file):
        self._deploy_app(mda_file)
        self.assert_app_running()

        # check if Fluentbit is running
        output = self.run_on_container("ps -ef| grep fluentbit")
        assert output is not None
        assert str(output).find("fluent-bit") >= 0

    def _test_fluentbit_not_running(self, mda_file):
        self._deploy_app(mda_file, splunk=False)
        self.assert_app_running()

        # check if Fluentbit is not running
        output = self.run_on_container("ps -ef| grep fluentbit")
        assert str(output).find("fluent-bit") == -1

    def _test_splunk_is_configured(self):
        self.assert_string_in_recent_logs("Splunk has been configured successfully.")

    def _test_splunk_is_not_configured(self):
        self.assert_patterns_not_in_recent_logs([SPLUNK_LOGS_PATTERN])

    def test_splunk_mx9(self):
        self._test_fluentbit_running("BuildpackTestApp-mx9-7.mda")
        self._test_splunk_is_configured()

    def test_splunk_not_configured(self):
        self._test_fluentbit_not_running("BuildpackTestApp-mx9-7.mda")
        self._test_splunk_is_not_configured()
