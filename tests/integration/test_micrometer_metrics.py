from tests.integration import basetest


class TestMicrometerMetricsFlow(basetest.BaseTestWithPostgreSQL):
    """Test the metrics flow when metrics via micrometer is enabled.

    Even with micrometer enabled, we still have the following list of metrics
    pushed to TSS via python metrics emitter:
    - database
    - storage
    - health
    - smaps
    - critical log count
    Here we assume the metrics are written to STDOUT with BYPASS_LOGGREGATOR
    set to false, which is not the case in production. These tests just ensure
    the correct metrics are still being emitted.

    Runtime stats like memory, threadpool are pushed to TSS via telegraf,
    which are not being tested here.
    """

    def test_free_apps_metrics(self):
        """Test no metrics for free apps via old stream."""
        self.stage_container(
            "BuildpackTestApp-mx9-7.mda",
            env_vars={
                "METRICS_INTERVAL": "10",
                "DISABLE_MICROMETER_METRICS": "false",
                "TRENDS_STORAGE_URL": "some-fake-url",
                "PROFILE": "free",
            },
        )
        self.start_container()
        self.assert_app_running()

        assert self.await_string_in_recent_logs("MENDIX-METRICS: ", 10)
        self.assert_string_not_in_recent_logs('named_user_sessions":')
        self.assert_string_not_in_recent_logs('anonymous_sessions":')
        self.assert_string_not_in_recent_logs('health":')
        self.assert_string_not_in_recent_logs('nativecode":')
        self.assert_string_not_in_recent_logs('critical_logs_count":')

    def test_paid_apps_metrics(self):
        """Test selected metrics for paid apps via old stream."""
        self.stage_container(
            "BuildpackTestApp-mx9-7.mda",
            env_vars={
                "METRICS_INTERVAL": "10",
                "DISABLE_MICROMETER_METRICS": "false",
                "TRENDS_STORAGE_URL": "some-fake-url",
            },
        )
        self.start_container()

        assert self.await_string_in_recent_logs("MENDIX-METRICS: ", 10)
        self.assert_string_in_recent_logs('indexes_size":')
        self.assert_string_in_recent_logs('number_of_files":')
        self.assert_string_in_recent_logs('health":')
        self.assert_string_in_recent_logs('nativecode":')
        self.assert_string_in_recent_logs('critical_logs_count":')
        self.assert_string_not_in_recent_logs('named_user_sessions":')
        self.assert_string_not_in_recent_logs('javaheap":')
        self.assert_string_not_in_recent_logs('codecache":')
        self.assert_string_not_in_recent_logs('requests":')
        self.assert_string_not_in_recent_logs('active_threads":')
