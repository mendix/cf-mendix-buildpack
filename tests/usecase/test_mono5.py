import basetest


class TestCaseMono5(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "AdoptOpenJDKTest_8beta3.mpk",
            env_vars={
                "DEPLOY_PASSWORD": self.mx_password,
                "DEVELOPMENT_MODE": True,
            },
        )
        self.startApp()

    def test_mono5(self):
        self.assert_app_running()
        self.assert_string_in_recent_logs("Selecting Mono Runtime: mono-5")
