import subprocess
import basetest
import time


class TestCaseEmitMetrics(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mda')
        subprocess.check_call(('cf', 'set-env', self.app_name, 'METRICS_INTERVAL', '10'))
        self.startApp()

    def test_read_metrics_in_logs(self):
        time.sleep(10)
        self.assert_string_in_recent_logs(self.app_name, 'MENDIX-METRICS: ')
        self.assert_string_in_recent_logs(self.app_name, 'critical_logs_count')
