import basetest


class TestCaseMdaAppDeployed(basetest.BaseTest):
    def setUp(self):
        self.setUpCF("sample-6.2.0.mda", instances=3)
        self.startApp()

    def test_mda_app_deployed_unauthorized(self):
        self.assert_app_running()
