import json
import os

import basetest


class TestCaseLogging(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "sample-6.2.0.mda",
            env_vars={"LOGGING_CONFIG": json.dumps({"Jetty": "TRACE"})},
        )
        self.startApp()

    def test_logging_config(self):
        self.assert_app_running()
        self.assert_string_in_recent_logs("TRACE - Jetty")

    def test_commit_hash_in_logs(self):
        commit_hash = None
        if os.getenv("TRAVIS_PULL_REQUEST") == "false":
            commit_hash = os.getenv("TRAVIS_COMMIT")
        else:
            commit_hash = os.getenv("TRAVIS_COMMIT_RANGE").split("...")[0]
        if commit_hash:
            short_commit_hash = commit_hash[:7]
            self.assert_string_in_recent_logs(short_commit_hash)
