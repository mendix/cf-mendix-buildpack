import os

from buildpack.telemetry import telegraf
from tests.integration import basetest


class TestCaseTelegraf(basetest.BaseTest):
    def _stage_test_app(self, env=None):
        """Stage a compatible test app for tests with telegraf"""
        # TODO : DISABLE_MICROMETER_METRICS would eventually be removed
        # once we go live with the micrometer metrics stream.
        if not env:
            env = {
                "TRENDS_STORAGE_URL": "some-fake-url",
                "DISABLE_MICROMETER_METRICS": "false",
            }
        self.stage_container(
            "BuildpackTestApp-mx9-7.mda",
            env_vars=env,
        )
        self.start_container()
        self.assert_app_running()

    def test_telegraf_running(self):
        """Ensure telegraf running when APPMETRICS_TARGET set"""
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"APPMETRICS_TARGET": '{"url": "https://foo.bar/write"}'},
        )
        self.start_container()
        self.assert_app_running()
        self.assert_listening_on_port(telegraf.get_statsd_port(), "telegraf")
        self.assert_string_not_in_recent_logs("E! [inputs.postgresql]")
        self.assert_string_not_in_recent_logs("E! [processors.")

    def test_telegraf_not_running_runtime_less_than_mx9_7(self):
        """Ensure telegraf is not running for runtimes less than 9.7.0

        Scenario where we have not enabled APPMETRICS_TARGET or Datadog.
        """
        self.stage_container(
            "BuildpackTestApp-mx9-6.mda",
        )
        self.start_container()
        self.assert_string_not_in_recent_logs("Starting Telegraf")

    def test_telegraf_not_running_runtime_mx9_7_force_disabled(self):
        """Ensure telegraf is not running for runtime 9.7.0 unless forced

        TODO : Temporary check to test the feature flag
        """
        self._stage_test_app(
            env={
                "DISABLE_MICROMETER_METRICS": "true",
            }
        )
        self.assert_string_not_in_recent_logs("Starting Telegraf")

    def test_telegraf_running_runtime_greater_than_mx9_7(self):
        """Ensure telegraf is running for runtimes greater than or equal to 9.7.0

        Starting runtime version 9.7.0, telegraf is expected to be
        enabled to handle metrics send from micrometer.
        """
        self._stage_test_app()
        self.await_string_in_recent_logs("Starting Telegraf", max_time=5)
        self.assert_running("telegraf")
        self.await_string_in_recent_logs(
            "Metrics: Adding metrics registry InfluxMeterRegistry", max_time=5
        )

    def test_telegraph_config_for_micrometer(self):
        """Ensure telegraf is configured to collect metrics from micrometer"""
        version = telegraf.VERSION
        telegraf_config_path = os.path.join(
            os.sep,
            "app",
            ".local",
            "telegraf",
            f"telegraf-{version}",
            "etc",
            "telegraf",
            "telegraf.conf",
        )
        self._stage_test_app()
        # Ensure we have the influxdb_listener plugin added
        output = self.run_on_container(
            "cat {} | grep -A2 inputs.influxdb_listener".format(
                telegraf_config_path
            )
        )
        assert output is not None
        assert str(output).find("influxdb_listener") >= 0

        # Ensure the trends-storage-url is set
        output = self.run_on_container(
            "cat {} | grep -A2 outputs.http".format(telegraf_config_path)
        )
        assert output is not None
        assert str(output).find("some-fake-url") >= 0

        # Ensure we have the appropriate headers
        output = self.run_on_container(
            "cat {} | grep -A5 outputs.http.headers".format(
                telegraf_config_path
            )
        )
        assert output is not None
        assert str(output).find("Micrometer-Metrics") >= 0
