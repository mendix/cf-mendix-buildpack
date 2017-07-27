import requests
import basetest


class TestCaseMxAdminExposed(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mpk')
        self.startApp()

    def test_mxadmin_exposed_unauthorized(self):
        full_uri = 'https://' + self.app_name + '/_mxadmin/'
        r = requests.get(full_uri)
        assert r.status_code == 401

    def test_mxadmin_exposed_authorized(self):
        full_uri = 'https://' + self.app_name + '/_mxadmin/'
        r = requests.get(full_uri, auth=('MxAdmin', self.mx_password))
        assert r.status_code == 200
