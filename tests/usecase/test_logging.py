import basetest
import subprocess
import json


class TestCaseLogging(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mda')
        logging_config = {
            "Jetty": "TRACE",
        }
        subprocess.check_call(('cf', 'set-env', self.app_name,
            'LOGGING_CONFIG', json.dumps(logging_config),
        ))
        self.startApp()

    def test_logging_config(self):
        self.assert_app_running(self.app_name)
        self.assert_string_in_recent_logs(self.app_name, 'TRACE - Jetty')
