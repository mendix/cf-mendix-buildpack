import json
import os

from tests.integration import basetest


class TestCaseLogging(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.stage_container(
            "sample-6.2.0.mda",
            env_vars={"LOGGING_CONFIG": json.dumps({"Jetty": "TRACE"})},
        )
        self.start_container()

    def test_logging_config(self):
        self.assert_app_running()
        self.assert_string_in_recent_logs("TRACE - Jetty")

    # TODO check if we even have to test this
    def test_commit_hash_in_logs(self):
        commit_hash = None
        if os.getenv("TRAVIS_PULL_REQUEST") == "false":
            commit_hash = os.getenv("TRAVIS_COMMIT")
        else:
            if os.getenv("TRAVIS_COMMIT_RANGE"):
                commit_hash = os.getenv("TRAVIS_COMMIT_RANGE").split("...")[0]
        if commit_hash:
            short_commit_hash = commit_hash[:7]
            self.assert_string_in_recent_logs(short_commit_hash)
