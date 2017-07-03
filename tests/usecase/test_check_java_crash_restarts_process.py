import subprocess
import basetest
import time


class TestCaseJavaCrashRestartsProcess(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mda')
        self.startApp()

    def test_check_java_crash_restarts_process(self):
        self.assert_app_running(self.app_name)
        subprocess.check_call(
            ('cf', 'ssh', self.app_name, '-c', 'killall java')
        )
        time.sleep(10)
        cf_events = subprocess.check_output(
            ('cf', 'events', self.app_name)
        )
        assert 'app.crash' in cf_events
