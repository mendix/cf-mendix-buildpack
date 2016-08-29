import requests
import os
import subprocess
import basetest


class TestCaseMxAdminExposed(basetest.BaseTest):
    _multiprocess_can_split_ = True

    def setUp(self):
        package_name = "sample-6.2.0.mpk"
        self.setUpCF(package_name)
        subprocess.check_call("cf start \"%s\"" % self.app_name, shell=True)

    def test_mxadmin_exposed_unauthorized(self):
        # assumes the app route is coming from env var
        full_uri = "https://" + self.app_name+ "/_mxadmin/"
        r = requests.get(full_uri)
        assert r.status_code == 401


    def test_mxadmin_exposed_authorized(self):
        # assumes the app route is coming from env var
        full_uri = "https://" + self.app_name + "/_mxadmin/"
        r = requests.get(full_uri, auth=('MxAdmin', self.mx_password))
        assert r.status_code == 200
