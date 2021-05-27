from tests.integration import basetest


class TestCaseTermination(basetest.BaseTest):

    # Tests if termination works if the runtime shuts down by itself
    def test_termination_runtime_intiated(self):
        self.stage_container("Mendix8.1.1.58432_StarterApp.mda")
        self.start_container()
        self.assert_app_running()
        self.query_mxadmin({"action": "shutdown"})
        self.assert_string_in_recent_logs("Mendix Runtime is shutting down")
        self.assert_string_in_recent_logs("Mendix Runtime is now shut down")
        assert self.await_container_status("unhealthy", 60)

    # Tests if the runtime is shut down gracefully on SIGTERM
    def test_termination_sigterm(self):
        self.stage_container("Mendix8.1.1.58432_StarterApp.mda")
        self.start_container()
        self.assert_app_running()
        self.terminate_container()
        self.assert_string_in_recent_logs("Mendix Runtime is shutting down")
        self.assert_string_in_recent_logs("Mendix Runtime is now shut down")
        assert self.await_container_status("unhealthy"), 60

    # Tests that the process terminates with a stack trace when Python code
    # errors. The env variable S3_ENCRYPTION_KEYS is used here, it doesn't
    # have a try-except on it.
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

    # Tests if a broken application terminates
    def test_termination_broken_application(self):
        self.stage_container(
            "Sample-StartError-7.23.2.mda",
            env_vars={"METRICS_INTERVAL": "10",},
        )
        self.start_container(status="unhealthy")
        self.assert_string_in_recent_logs("start failed")
        self.assert_string_not_in_recent_logs("health check never passed")

    # Tests if killing Java terminates the container
    def test_termination_java_crash_triggers_unhealthy(self):
        self.stage_container(
            "sample-6.2.0.mda", env_vars={"METRICS_INTERVAL": "10",},
        )
        self.start_container()
        self.assert_app_running()
        self.run_on_container("killall java")
        assert self.await_container_status("unhealthy", 60)
