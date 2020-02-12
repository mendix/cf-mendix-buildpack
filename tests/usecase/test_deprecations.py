import basetest


class TestCaseDeprecationMx5MPK(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "mx5.3.2_app.mpk",
            env_vars={
                "DEPLOY_PASSWORD": self.mx_password,
                "DEVELOPMENT_MODE": True,
            },
        )

    def test_mx5_mpk(self):
        self.startApp(expect_failure=True)
        self.assert_string_in_recent_logs(
            "Mendix Runtime 5.x is no longer supported"
        )


class TestCaseDeprecationMx5MDA(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "mx5.3.2_app.mda",
            env_vars={
                "DEPLOY_PASSWORD": self.mx_password,
                "DEVELOPMENT_MODE": True,
            },
        )

    def test_mx5_mda(self):
        self.startApp(expect_failure=True)
        self.assert_string_in_recent_logs(
            "Mendix Runtime 5.x is no longer supported"
        )
