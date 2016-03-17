import requests
import basetest
import subprocess

class TestCaseMpkAppDeployed(basetest.BaseTest):

    def setUp(self):
        package_name = "sample-6.2.0.mpk"
        self.setUpCF(package_name)
        subprocess.check_call("cf start \"%s\"" % self.app_name, shell=True)
    def test_mpk_app_deployed_unauthorized(self):
        # assumes the app route is coming from env var
        full_uri = "https://" + self.app_name + "/xas/"
        r = requests.get(full_uri)
        assert r.status_code == 401
