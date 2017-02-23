import subprocess
import basetest
import json


class TestCaseConstants(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mda')
        # has more precedence
        subprocess.check_call((
            'cf', 'set-env', self.app_name,
            'MX_AppCloudServices_OpenIdProvider',
            'http://localhost'
        ))
        # over this one
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
        # this is enough because google.com would *always* respond
        self.assert_string_in_recent_logs(
            self.app_name,
            'java.net.ConnectException: Connection refused'
        )
