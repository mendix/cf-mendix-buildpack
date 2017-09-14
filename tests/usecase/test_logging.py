import basetest
import json


class TestCaseLogging(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mda', env_vars={
            'LOGGING_CONFIG': json.dumps({'Jetty': 'TRACE'}),
        })
        self.startApp()

    def test_logging_config(self):
        self.assert_app_running()
        self.assert_string_in_recent_logs('TRACE - Jetty')
