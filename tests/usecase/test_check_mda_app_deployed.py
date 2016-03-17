import basetest
import subprocess


class TestCaseMdaAppDeployed(basetest.BaseTest):

    def setUp(self):
        package_name = "sample-6.2.0.mda"
        self.setUpCF(package_name)
        subprocess.check_call("cf start \"%s\"" % self.app_name, shell=True)

    def test_mda_app_deployed_unauthorized(self):
        self.assert_app_running(self.app_name)
