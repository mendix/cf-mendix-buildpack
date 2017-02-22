import subprocess
import basetest
import json


class TestCaseConstants(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mda')
        subprocess.check_call((
            'cf', 'set-env', self.app_name,
            'MX_AppCloudServices_OpenIdProvider',
            'http://localhost'
        ))
        subprocess.check_call((
            'cf', 'set-env', self.app_name,
            'CONSTANTS',
            json.dumps({
                "AppCloudServices.OpenIdEnabled": True,
                "AppCloudServices.OpenIdProvider": "http://google.com/"
            })
        ))
        self.startApp()

    def test_constant_is_set(self):
        self.assert_string_in_recent_logs(
            self.app_name,
            'Connection to http://localhost refused'
        )
