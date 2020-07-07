from tests.integration import basetest


class TestCaseTelegraf(basetest.BaseTest):
    def test_telegraf_running(self):
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"APPMETRICS_TARGET": '{"url": "https://foo.bar/write"}'},
        )
        self.start_container()

        self.assert_app_running()

        # Validate telegraf is running and has port 8125 opened for StatsD
        output = self.run_on_container("lsof -i | grep '^telegraf.*:8125'")
        assert output and str(output).find("telegraf") >= 0
