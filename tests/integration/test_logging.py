import json

from tests.integration import basetest


class TestCaseLogging(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.stage_container(
            "Mendix8.1.1.58432_StarterApp.mda",
            env_vars={
                "LOGGING_CONFIG": json.dumps({"Jetty": "TRACE"}),
                "LOG_RATELIMIT": 500,
            },
        )
        self.start_container()

    def test_logging_config(self):
        self.assert_app_running()
        self.assert_string_in_recent_logs("TRACE - Jetty")
