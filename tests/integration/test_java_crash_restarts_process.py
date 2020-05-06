import backoff

from tests.integration import basetest


class TestCaseJavaCrashRestartsProcess(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "sample-6.2.0.mda",
            env_vars={
                "DEPLOY_PASSWORD": self.mx_password,
                "METRICS_INTERVAL": "10",
            },
        )
        self.startApp()

    def test_java_crash_restarts_process(self):
        self.assert_app_running()
        print("killing java to see if app will actually restart")
        self.cmd(("cf", "ssh", self.app_name, "-c", "killall java"))

        found = self._await_crash_in_cf_events("app.crash")
        if not found:
            print(self.cmd(("cf", "events", self.app_name)))
        assert found

    @backoff.on_predicate(backoff.expo, lambda x: not x, max_time=180)
    def _await_crash_in_cf_events(self, needle):
        return needle in self.cmd(("cf", "events", self.app_name))
