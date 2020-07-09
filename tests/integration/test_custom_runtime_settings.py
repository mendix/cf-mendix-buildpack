import json

from tests.integration import basetest

# TODO check if can be unit tested
class TestCaseCustomRuntimeSettings(basetest.BaseTest):
    def test_custom_runtime_setting_is_set(self):
        self.stage_container(
            "sample-6.2.0.mda",
            env_vars={
                "MXRUNTIME_PersistentSessions": "True",
                "CUSTOM_RUNTIME_SETTINGS": json.dumps(
                    {"SourceDatabaseType": "MySQL"}
                ),
            },
        )
        with self.assertRaises(RuntimeError):
            self.start_container()
        self.assert_string_in_recent_logs("MySQL")
