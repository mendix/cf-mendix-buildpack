import basetest
import subprocess


class TestCaseMpkAppDeployed(basetest.BaseTest):
    def setUp(self):
        self.setUpCF(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"APPMETRICS_TARGET": '{"url": "https://foo.bar/write"}'},
        )
        self.startApp()

    def test_telegraf_running(self):
        self.assert_app_running()

        # Validate telegraf is running and has port 8125 opened for StatsD
        output = subprocess.check_output(
            "cf ssh %s -c \"lsof -i | grep '^telegraf.*:8125'\""
            % self.app_name,
            stderr=subprocess.STDOUT,
            shell=True,
        )
        assert output is not None
        assert str(output).find("telegraf") >= 0
