import json
import os
import unittest

from buildpack import nginx


class TestCaseNginxBinPath(unittest.TestCase):
    def test_default_nginx_bin_path(self):
        del os.environ["NGINX_CUSTOM_BIN_PATH"]
        nginx_bin_path = nginx.get_nginx_bin_path()
        self.assertEquals("nginx/sbin/nginx", nginx_bin_path)

    def test_custom_nginx_bin_path(self):
        os.environ["NGINX_CUSTOM_BIN_PATH"] = "/usr/sbin/nginx"
        nginx_bin_path = nginx.get_nginx_bin_path()
        self.assertEquals("/usr/sbin/nginx", nginx_bin_path)
