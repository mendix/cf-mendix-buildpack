import basetest
import subprocess

class TestCaseMpkAppDeployed(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('BuildpackTestApp-mx-7-16.mda', env_vars={
            'APPMETRICS_TARGET': '{"url": "https://foo.bar/write"}',
            'DD_API_KEY': 'NON-VALID-TEST-KEY'
        })
        self.startApp()

    def test_telegraf_running(self):
        self.assert_app_running()

        # Validate telegraf is running and has port 8125 opened for StatsD
        tg_output = subprocess.check_output(
            'cf ssh %s -c "lsof -i | grep \'^telegraf.*:8125\'"' % self.app_name,
            stderr=subprocess.STDOUT,
            shell=True
        )
        assert tg_output is not None
        assert str(tg_output).find('telegraf') >= 0

        dd_output = subprocess.check_output(
            'cf ssh %s -c "ps x | grep \'\\\.local/datadog/datadog-agent\'" ' % self.app_name,
            stderr=subprocess.STDOUT,
            shell=True
        )
        assert dd_output is not None
