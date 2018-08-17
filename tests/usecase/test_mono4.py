import basetest


class TestCaseMono4(basetest.BaseTest):
    def setUp(self):
        self.setUpCF(
            "MontBlancApp720.mpk",
            env_vars={"DEPLOY_PASSWORD": self.mx_password},
        )
        self.startApp()

    def test_mono4(self):
        self.assert_app_running()
        self.assert_string_in_recent_logs("Selecting Mono Runtime: mono-4")
