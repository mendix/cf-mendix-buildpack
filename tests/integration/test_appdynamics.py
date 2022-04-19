from tests.integration import basetest


class TestCaseDeployWithAppdynamics(basetest.BaseTest):
    def _deploy_app(self, mda_file, appdynamics_machine_agent_enabled="true"):
        super().setUp()
        self.stage_container(
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
                "APPDYNAMICS_MACHINE_AGENT_ENABLED": appdynamics_machine_agent_enabled,
            },
        )
        self.start_container()

    def _test_appdynamics_running(self, mda_file):
        self._deploy_app(mda_file)
        self.assert_app_running()

        # check if appdynamics agent is running
        output = self.run_on_container("ps -ef| grep javaagent")
        assert output is not None
        assert str(output).find("appdynamics") >= 0

        # check if machine agent is running
        output = self.run_on_container("ps -ef | grep machineagent")
        assert output is not None
        assert str(output).find("Dmetric.http.listener=true") >= 0

    def _test_appdynamics(self, mda_file):
        self._test_appdynamics_running(mda_file)
        self.assert_string_in_recent_logs(
            "Started AppDynamics Java Agent Successfully"
        )

    def test_appdynamics_mx9(self):
        self._test_appdynamics("BuildpackTestApp-mx9-7.mda")

    def test_appdynamics_mx8(self):
        self._test_appdynamics("Mendix8.1.1.58432_StarterApp.mda")

    def test_appdynamics_mx7(self):
        self._test_appdynamics("BuildpackTestApp-mx-7-16.mda")

    def test_appdynamics_mx6(self):
        self._test_appdynamics("sample-6.2.0.mda")

    def test_machine_agent_not_started(self):

        self._deploy_app(
            "BuildpackTestApp-mx9-7.mda",
            appdynamics_machine_agent_enabled="false",
        )
        self.assert_app_running()

        # Check that AppDynamics Machine Agent is not run

        output = self.run_on_container("ps -ef | grep machineagent")
        assert str(output).find("Dmetric.http.listener=true") == -1
