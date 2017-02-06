import basetest
import subprocess
import requests
import time


class TestCaseMono4(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('mono4-7-build20010.mpk')
        subprocess.check_call(('cf', 'set-env', self.app_name, 'DEPLOY_PASSWORD', self.mx_password))
        self.startApp()

    def test_mono4(self):
        self.assert_app_running(self.app_name)
        self.assert_string_in_recent_logs(self.app_name, 'Selecting Mono Runtime: mono-4')
