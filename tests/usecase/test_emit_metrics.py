import basetest
import time


class TestCaseEmitMetrics(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mda', env_vars={
            'METRICS_INTERVAL': '10',
        })
        self.startApp()

    def test_read_metrics_in_logs(self):
        time.sleep(10)
        self.assert_string_in_recent_logs('MENDIX-METRICS: ')
        self.assert_string_in_recent_logs('storage')
        self.assert_string_in_recent_logs('number_of_files')
        self.assert_string_in_recent_logs('critical_logs_count')
