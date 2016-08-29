import basetest
import subprocess
import requests
import time


class TestCaseFastdeploy(basetest.BaseTest):
    _multiprocess_can_split_ = True

    def setUp(self):
        package_name_b = "MontBlancApp671b.mpk"
        package_url_b = "https://s3-eu-west-1.amazonaws.com/mx-ci-binaries/" + package_name_b
        cmd = "wget -O \"%s\" \"%s\"" % (package_name_b, package_url_b)
        subprocess.check_call(cmd, shell=True)

        package_name = "MontBlancApp671.mpk"
        self.setUpCF(package_name)
        subprocess.check_call("cf set-env \"%s\" DEPLOY_PASSWORD \"%s\"" % (self.app_name, self.mx_password), shell=True)
        subprocess.check_call("cf start \"%s\"" % self.app_name, shell=True)

    def test_fast_deploy(self):
        full_uri = "https://" + self.app_name + "/_mxbuild/"
        files = {'file': open('MontBlancApp671b.mpk', 'rb')}
        time.sleep(10)
        r = requests.post(full_uri, auth=('deploy', self.mx_password), files=files)
        assert r.status_code == 200
        assert "STARTED" in r.text
