from tests.integration import basetest


class TestCaseDeployWithMetering(basetest.BaseTestWithPostgreSQL):
    def _deploy_app(self, mda_file):
        self.stage_container(
            mda_file,
            env_vars={
                "MXUMS_SUBSCRIPTION_SECRET": "NON-VALID-SUB-SECRET",
                "MXUMS_ENVIRONMENT_NAME": "TEST-ENV",
                "MXUMS_LICENSESERVER_URL": "http://localhost:5000/v3/activate",
            },
        )
        self.start_container()

    def _test_metering_running(self, mda_file):
        self._deploy_app(mda_file)
        self.assert_app_running()
        output = self.run_on_container("ps -ef | grep 'metering-sidecar'")
        assert output is not None
        assert (
            str(output).find("/home/vcap/app/metering/metering-sidecar") >= 0
        )

        self.assert_string_in_recent_logs("Scheduling call home every 43200s")

    def test_metering_mx8(self):
        self._test_metering_running("Mendix8.1.1.58432_StarterApp.mda")

    def test_metering_mx7(self):
        self._test_metering_running("BuildpackTestApp-mx-7-16.mda")

    def test_metering_mx6(self):
        self._test_metering_running("sample-6.2.0.mda")

    def test_metering_sidecar_failure(self):
        self.stage_container(
            "Mendix8.1.1.58432_StarterApp.mda",
            env_vars={
                "MXUMS_LICENSESERVER_URL": "http://localhost:5000/v3/activate",
            },
        )
        self.start_container()
        self.assert_app_running()
