import basetest
import subprocess


class TestCaseMpkAppDeployed(basetest.BaseTest):

    def setUp(self):
        package_name = "sample-6.2.0.mpk"
        self.setUpCF(package_name)
        subprocess.check_call("cf start \"%s\"" % self.app_name, shell=True)

    def test_mpk_app_deployed_unauthorized(self):
        self.assert_app_running(self.app_name)
