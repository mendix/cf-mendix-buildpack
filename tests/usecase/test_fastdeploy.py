import basetest
import subprocess
import requests
import time


class TestCaseFastdeploy(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('MontBlancApp671.mpk')
        subprocess.check_call(('cf', 'set-env', self.app_name, 'DEPLOY_PASSWORD', self.mx_password))
        self.startApp()

    def test_fast_deploy(self):
        subprocess.check_call(('wget', 'https://s3-eu-west-1.amazonaws.com/mx-ci-binaries/MontBlancApp671b.mpk'))
        full_uri = "https://" + self.app_name + "/_mxbuild/"
        time.sleep(10)
        r = requests.post(full_uri, auth=('deploy', self.mx_password), files={
            'file': open('MontBlancApp671b.mpk', 'rb'),
        })

        if r.status_code != 200:
            print(self.get_recent_logs())
            print(r.text)
        assert r.status_code == 200
        assert "STARTED" in r.text
