import basetest
import json


class TestCaseCustomRuntimeSettings(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "sample-6.2.0.mda",
            health_timeout=60,
            env_vars={
                "MXRUNTIME_PersistentSessions": "True",
                "CUSTOM_RUNTIME_SETTINGS": json.dumps(
                    {"SourceDatabaseType": "MySQL"}
                ),
            },
        )
        self.startApp(expect_failure=True)

    def test_custom_runtime_setting_is_set(self):
        self.assert_string_in_recent_logs("MySQL")
