import unittest
import requests
import os


class TestCaseMxAdminExposed(unittest.TestCase):
    def test_mxadmin_exposed_unauthorized(self):
        # assumes the app route is coming from env var
        app_name = os.environ.get("APP_NAME")
        full_uri = "https://" + app_name + "." + os.environ.get("CF_DOMAIN") + "/_mxadmin/"

        r = requests.get(full_uri)
        assert r.status_code == 401


    def test_mxadmin_exposed_authorized(self):
        # assumes the app route is coming from env var
        app_name = os.environ.get("APP_NAME")
        full_uri = "https://" + app_name + "." + os.environ.get("CF_DOMAIN") + "/_mxadmin/"

        r = requests.get(full_uri, auth=('MxAdmin', os.environ.get("MX_PASSWORD")))
        assert r.status_code == 200
