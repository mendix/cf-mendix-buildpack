from tests.integration import basetest


class TestCaseDeprecationMx5(basetest.BaseTest):
    def test_mx5_mpk(self):
        with self.assertRaises(RuntimeError):
            self.stage_container(
                "mx5.3.2_app.mpk",
                env_vars={
                    "DEPLOY_PASSWORD": self._mx_password,
                    "DEVELOPMENT_MODE": True,
                },
            )

    def test_mx5_mda(self):
        with self.assertRaises(RuntimeError):
            self.stage_container(
                "mx5.3.2_app.mda",
                env_vars={
                    "DEPLOY_PASSWORD": self._mx_password,
                    "DEVELOPMENT_MODE": True,
                },
            )
