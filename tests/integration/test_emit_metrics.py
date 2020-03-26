import time

from tests.integration import basetest


class TestCaseEmitMetrics(basetest.BaseTest):
    # Integration tests for metrics emission.

    # At the moment these tests rely on the fact that metrics are emitted via
    # stdout, when BYPASS_LOGGREGATOR and the trends-storage-server URL
    # environment variables are both set. In production we don't actually emit
    # metrics over stdout, so these tests don't accurately test the production
    # situation. However it is sufficient to prove that the metrics emitter
    # threads work as expected, just not that the metrics get to the right
    # destination.

    def setUp(self):
        super().setUp()
        self.setUpCF("sample-6.2.0.mda", env_vars={"METRICS_INTERVAL": "10"})
        self.startApp()

    def test_read_metrics_in_logs(self):
        time.sleep(10)
        self.assert_string_in_recent_logs("MENDIX-METRICS: ")
        self.assert_string_in_recent_logs("storage")
        self.assert_string_in_recent_logs("number_of_files")
        self.assert_string_in_recent_logs("critical_logs_count")

    def test_free_apps_metrics(self):
        self.setUpCF(
            "sample-6.2.0.mda",
            env_vars={"METRICS_INTERVAL": "10", "PROFILE": "free"},
        )
        self.startApp()

        time.sleep(10)
        self.assert_string_in_recent_logs("MENDIX-METRICS: ")
        self.assert_string_in_recent_logs("named_users")
        self.assert_string_in_recent_logs("anonymous_sessions")
        self.assert_string_in_recent_logs("named_user_sessions")


class TestNewMetricsFlows(basetest.BaseTest):
    def test_fallback_flow_when_server_unreachable(self):
        self.setUpCF(
            "sample-6.2.0.mda",
            env_vars={
                "METRICS_INTERVAL": "10",
                "BYPASS_LOGGREGATOR": "True",
                # This should always 404:
                "TRENDS_STORAGE_URL": "https://example.com/a_fake_path",
                "BUILDPACK_XTRACE": "true",
            },
        )
        self.startApp()

        time.sleep(10)
        self.assert_string_in_recent_logs(
            "Failed to send metrics to trends server"
        )
        self.assert_string_in_recent_logs("MENDIX-METRICS: ")

    def test_fallback_when_no_url_set(self):
        self.setUpCF(
            "sample-6.2.0.mda",
            env_vars={"METRICS_INTERVAL": "10", "BYPASS_LOGGREGATOR": "True"},
        )
        self.startApp()

        time.sleep(10)
        self.assert_string_in_recent_logs(
            "BYPASS_LOGGREGATOR is set to true, but no metrics URL is "
            "set. Falling back to old loggregator-based metric reporting."
        )
        self.assert_string_in_recent_logs("MENDIX-METRICS: ")

    def test_fallback_with_bad_environment_variables(self):
        self.setUpCF(
            "sample-6.2.0.mda",
            env_vars={
                "METRICS_INTERVAL": "10",
                "BYPASS_LOGGREGATOR": "this will not coerce to a boolean",
            },
        )
        self.startApp()

        time.sleep(10)
        self.assert_string_in_recent_logs(
            "Bypass loggregator has a nonsensical value"
        )
        self.assert_string_in_recent_logs("MENDIX-METRICS: ")

    def test_posting_metrics_works(self):
        self.setUpCF(
            "sample-6.2.0.mda",
            env_vars={
                "METRICS_INTERVAL": "10",
                "BYPASS_LOGGREGATOR": "True",
                "TRENDS_STORAGE_URL": "http://httpbin.org/post",
            },
        )
        self.startApp()

        time.sleep(10)
        self.assert_string_not_in_recent_logs("MENDIX-METRICS: ")
