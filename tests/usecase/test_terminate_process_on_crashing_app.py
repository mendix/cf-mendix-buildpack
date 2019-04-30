import basetest


class TestCaseTerminateChildProcessesCompleteOnCrashingApp(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "Sample-StartError-7.23.2.mda",
            health_timeout=60,
            env_vars={
                "DEPLOY_PASSWORD": self.mx_password,
                "METRICS_INTERVAL": "10",
            },
        )

    def test_verify_termination_logs(self):
        self.startApp(expect_failure=True, start_timeout=5)
        self.assert_string_in_recent_logs("start failed, stopping")
        self.assert_string_not_in_recent_logs("health check never passed")
