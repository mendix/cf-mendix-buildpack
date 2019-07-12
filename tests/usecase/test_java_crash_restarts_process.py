import basetest
import time


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
        time.sleep(10)
        cf_events = self.cmd(("cf", "events", self.app_name))
        print("checking if process has crashed in cf events")
        print(cf_events)
        assert "app.crash" in cf_events
