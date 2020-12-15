import json

from tests.integration import basetest

# TODO: check if we can unit test this
class TestCaseJettyConfig(basetest.BaseTest):
    def test_jetty_config(self):
        self.stage_container(
            "sample-6.2.0.mda",
            env_vars={
                "BUILDPACK_XTRACE": "true",
                "JETTY_CONFIG": json.dumps({"runtime_max_threads": 500}),
            },
        )
        self.start_container()
        self.assert_string_in_recent_logs("runtime_max_threads")
        self.assert_string_in_recent_logs("max_form_content_size")

    def test_invalid_jetty_config(self):
        self.stage_container(
            "sample-6.2.0.mda", env_vars={"JETTY_CONFIG": "invalid json"}
        )
        self.start_container()
        self.assert_string_in_recent_logs("Failed to configure jetty")
