import basetest


class TestCaseMpkAppDeployed(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mpk')
        self.startApp()

    def test_mpk_app_deployed_unauthorized(self):
        self.assert_app_running(self.app_name)
