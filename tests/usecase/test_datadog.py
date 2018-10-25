import basetest


class TestCaseMpkAppDeployed(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"DD_API_KEY": "NON-VALID-TEST-KEY"},
        )
        self.startApp()

    def test_telegraf_running(self):
        self.assert_app_running()

        # Validate telegraf is running and has port 8125 opened for StatsD
        output = self.cmd(
            (
                "cf",
                "ssh",
                self.app_name,
                "-c",
                "lsof -i | grep '^datadog.*:8125'",
            )
        )
        assert output is not None
        assert str(output).find("datadog") >= 0
