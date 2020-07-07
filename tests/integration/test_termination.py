from tests.integration import basetest


class TestCaseTermination(basetest.BaseTest):

    # Tests that the process terminates with a stack trace when Python code
    # errors. The env variable S3_ENCRYPTION_KEYS is used here, it doesn't
    # have a try-except on it.
    # TODO determine if we can unit test this / should test this
    def test_termination_stacktrace(self):
        self.stage_container(
            "Mendix8.1.1.58432_StarterApp.mda",
            env_vars={"S3_ENCRYPTION_KEYS": "{invalid-json}"},
        )
        with self.assertRaises(RuntimeError):
            self.start_container()
        self.assert_string_in_recent_logs(
            'json.loads(os.getenv("S3_ENCRYPTION_KEYS"))'
        )

    def test_termination_broken_application(self):
        self.stage_container(
            "Sample-StartError-7.23.2.mda",
            env_vars={
                "DEPLOY_PASSWORD": self._mx_password,
                "METRICS_INTERVAL": "10",
            },
        )
        self.start_container(status="unhealthy")
        self.assert_string_in_recent_logs("start failed, stopping")
        self.assert_string_not_in_recent_logs("health check never passed")

    def test_java_crash_triggers_unhealthy(self):
        self.stage_container(
            "sample-6.2.0.mda",
            env_vars={
                "DEPLOY_PASSWORD": self._mx_password,
                "METRICS_INTERVAL": "10",
            },
        )
        self.start_container()
        self.assert_app_running()
        self.run_on_container("killall java")

        assert self.await_container_status("unhealthy", 60)
