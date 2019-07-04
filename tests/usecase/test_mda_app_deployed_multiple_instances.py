import basetest


class TestCaseMdaAppDeployed(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF("BuildpackTestApp-mx-7-16.mda", instances=3)
        self.startApp()

    def test_mda_app_deployed_unauthorized(self):
        self.assert_app_running()
