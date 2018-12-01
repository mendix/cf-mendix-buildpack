import basetest


class TestCaseMdaAppDeployed(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF("sample-6.2.0.mda")
        self.startApp()

    def test_mda_app_deployed_unauthorized(self):
        self.assert_app_running()
