import json
import os
import unittest

from buildpack import nginx


class TestCaseNginxBinPath(unittest.TestCase):
    def test_default_nginx_bin_path(self):
        del os.environ["NGINX_CUSTOM_BIN_PATH"]
        nginx_bin_path = nginx.get_nginx_bin_path()
        is_custom_nginx = nginx.is_custom_nginx()
        self.assertEquals("nginx/sbin/nginx", nginx_bin_path)
        self.assertFalse(is_custom_nginx)

    def test_custom_nginx_bin_path(self):
        os.environ["NGINX_CUSTOM_BIN_PATH"] = "/usr/sbin/nginx"
        nginx_bin_path = nginx.get_nginx_bin_path()
        is_custom_nginx = nginx.is_custom_nginx()
        self.assertEquals("/usr/sbin/nginx", nginx_bin_path)
        self.assertTrue(is_custom_nginx)
