import basetest


class TestCaseDeployWithAppdynamics(basetest.BaseTest):
    def _deploy_app(self, mda_file):
        super().setUp()
        self.setUpCF(
            mda_file,
            env_vars={
                "APPDYNAMICS_AGENT_ACCOUNT_NAME": "Mendix-test",
                "APPDYNAMICS_AGENT_ACCOUNT_ACCESS_KEY": "NON-VALID-TEST-KEY",
                "APPDYNAMICS_AGENT_APPLICATION_NAME": "Test",
                "APPDYNAMICS_AGENT_NODE_NAME": "Test",
                "APPDYNAMICS_AGENT_TIER_NAME": "Test",
                "APPDYNAMICS_CONTROLLER_HOST_NAME": "test.mendix.com",
                "APPDYNAMICS_CONTROLLER_PORT": 443,
                "APPDYNAMICS_CONTROLLER_SSL_ENABLED": "true",
            },
        )
        self.startApp()

    def _test_appdynamics_running(self, mda_file):
        APPDYNAMICS_VERSION = "20.3.0.29587"
        self._deploy_app(mda_file)
        self.assert_app_running()

        # check if appdynamics agent is running
        output = self.cmd(
            ("cf", "ssh", self.app_name, "-c", "ps -ef| grep javaagent")
        )
        assert output is not None
        assert str(output).find(APPDYNAMICS_VERSION) >= 0

    def _test_appdynamics(self, mda_file):
        self._test_appdynamics_running(mda_file)
        self.assert_string_in_recent_logs(
            "Started AppDynamics Java Agent Successfully"
        )

    def test_appdynamics_mx8(self):
        self._test_appdynamics("Mendix8.1.1.58432_StarterApp.mda")

    def test_appdynamics_mx7(self):
        self._test_appdynamics("BuildpackTestApp-mx-7-16.mda")

    def test_appdynamics_mx6(self):
        self._test_appdynamics("sample-6.2.0.mda")
