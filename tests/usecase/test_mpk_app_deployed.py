import basetest


class TestCaseMpkAppDeployed(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF("MontBlancApp720.mpk")
        self.startApp()

    def test_mpk_app_deployed_unauthorized(self):
        self.assert_app_running()
