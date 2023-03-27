from tests.integration import basetest


class TestCaseTermination(basetest.BaseTest):
    def _test_termination_signal(self, signal="SIGTERM", env_vars=None, exitcode=0):
        self.stage_container("Mendix8.1.1.58432_StarterApp.mda", env_vars=env_vars)
        self.start_container()
        self.assert_app_running()
        self.terminate_container(signal=signal)
        self.assert_shutdown(exitcode=exitcode)

    # Tests if the runtime is shut down gracefully on SIGTERM
    def test_termination_sigterm(self):
        self._test_termination_signal()

    # Tests if the runtime is shut down gracefully on SIGUSR1 without metrics enabled
    def test_termination_sigusr(self):
        self._test_termination_signal(signal="SIGUSR1", exitcode=1)
        self.assert_string_in_recent_logs("SIGUSR1 received")

    # Tests if the runtime is shut down gracefully on SIGUSR1 with metrics enabled
    def test_termination_sigusr_with_metrics(self):
        self._test_termination_signal(
            signal="SIGUSR1", exitcode=1, env_vars={"METRICS_INTERVAL": "10"}
        )
        self.assert_string_in_recent_logs("SIGUSR1 received")
        self.assert_string_in_recent_logs("Handling user signal for metrics...")

    # Tests if termination works if a shutdown command is sent to the runtime
    def test_termination_shutdown_command(self):
        self.stage_container("Mendix8.1.1.58432_StarterApp.mda")
        self.start_container()
        self.assert_app_running()
        self.query_mxadmin({"action": "shutdown"})
        self.assert_shutdown()

    # Tests that the process terminates with a stack trace when Python code
    # errors. The env variable S3_ENCRYPTION_KEYS is used here, it doesn't
    # have a try-except on it.
    def test_termination_stacktrace(self):
        self.stage_container(
            "Mendix8.1.1.58432_StarterApp.mda",
            env_vars={"S3_ENCRYPTION_KEYS": "{invalid-json}"},
        )
        with self.assertRaises(RuntimeError):
            self.start_container(start_timeout=30)
        self.assert_string_in_recent_logs('json.loads(os.getenv("S3_ENCRYPTION_KEYS"))')
        assert self.get_container_exitcode() == 1

    # Tests if a broken application terminates
    def test_termination_broken_application(self):
        self.stage_container(
            "Sample-StartError-7.23.2.mda",
            env_vars={
                "METRICS_INTERVAL": "10",
            },
        )
        self.start_container(health="unhealthy")
        self.assert_string_in_recent_logs("start failed")
        self.assert_string_not_in_recent_logs("health check never passed")
        self.assert_shutdown(1)

    # Tests if killing Java terminates the container
    def test_termination_java_crash_triggers_unhealthy(self):
        self.stage_container(
            "sample-6.2.0.mda",
            env_vars={
                "METRICS_INTERVAL": "10",
            },
        )
        self.start_container()
        self.assert_app_running()
        self.run_on_container("killall java")
        assert self.await_container_health("unhealthy", 60)
        self.assert_string_in_recent_logs("Runtime process has been terminated")
        assert self.get_container_exitcode() == 0  # A manual kill command is all fine
