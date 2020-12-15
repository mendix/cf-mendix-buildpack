from tests.integration import basetest


class TestCaseTelegrafDatadog(basetest.BaseTest):
    def test_telegraf_datadog_running(self):
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={
                "APPMETRICS_TARGET": '{"url": "https://foo.bar/write"}',
                "DD_API_KEY": "NON-VALID-TEST-KEY",
            },
        )
        self.start_container()
        self.assert_app_running()

        # Validate telegraf is running and has port 8125 opened for StatsD
        tg_output = self.run_on_container("lsof -i | grep '^telegraf.*:8125'",)
        assert tg_output is not None
        assert str(tg_output).find("telegraf") >= 0

        dd_output = self.run_on_container(
            "ps x | grep '\\.local/datadog/datadog-agent'",
        )
        assert dd_output is not None
