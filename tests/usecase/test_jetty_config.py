import basetest
import json


class TestCaseJettyConfig(basetest.BaseTest):
    def test_jetty_config(self):
        self.setUpCF(
            "sample-6.2.0.mda",
            env_vars={
                "BUILDPACK_XTRACE": "true",
                "JETTY_CONFIG": json.dumps({"runtime_max_threads": 500}),
            },
        )
        self.startApp()
        self.assert_string_in_recent_logs("runtime_max_threads")
        self.assert_string_in_recent_logs("max_form_content_size")

    def test_invalid_jetty_config(self):
        self.setUpCF(
            "sample-6.2.0.mda", env_vars={"JETTY_CONFIG": "invalid json"}
        )
        self.startApp()
        self.assert_string_in_recent_logs("Failed to configure jetty")
