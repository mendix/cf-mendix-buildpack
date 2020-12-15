from tests.integration import basetest


class TestCaseMdaAppDeployed(basetest.BaseTest):
    def test_mda_app_deployed_unauthorized(self):
        self.stage_container("sample-6.2.0.mda")
        self.start_container()
        self.assert_app_running()
