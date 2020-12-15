from tests.integration import basetest


class TestCaseMono(basetest.BaseTest):
    def test_mono4_present(self):
        assert (
            "Mono available: /tmp/opt/mono-4"
            in self.stage_container(
                "MontBlancApp720.mpk",
                env_vars={
                    "DEPLOY_PASSWORD": self._mx_password,
                    "DEVELOPMENT_MODE": True,
                },
            )[0]
        )

    def test_mono5_present(self):
        assert (
            "Mono available: /tmp/opt/mono-5"
            in self.stage_container(
                "AdoptOpenJDKTest_8beta3.mpk",
                env_vars={
                    "DEPLOY_PASSWORD": self._mx_password,
                    "DEVELOPMENT_MODE": True,
                },
            )[0]
        )
