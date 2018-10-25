import basetest


class TestCaseMpkAppDeployed(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={
                "APPMETRICS_TARGET": '{"url": "https://foo.bar/write"}',
                "DD_API_KEY": "NON-VALID-TEST-KEY",
            },
        )
        self.startApp()

    def test_telegraf_running(self):
        self.assert_app_running()

        # Validate telegraf is running and has port 8125 opened for StatsD
        tg_output = self.cmd(
            (
                "cf",
                "ssh",
                self.app_name,
                "-c",
                "lsof -i | grep '^telegraf.*:8125'",
            )
        )
        assert tg_output is not None
        assert str(tg_output).find("telegraf") >= 0

        dd_output = self.cmd(
            (
                "cf",
                "ssh",
                self.app_name,
                "-c",
                "ps x | grep '\\.local/datadog/datadog-agent'",
            )
        )
        assert dd_output is not None
