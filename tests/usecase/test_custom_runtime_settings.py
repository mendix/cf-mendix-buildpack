import basetest
import json


class TestCaseCustomRuntimeSettings(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mda', env_vars={
            'MXRUNTIME_PersistentSessions': 'True',
            'CUSTOM_RUNTIME_SETTINGS': json.dumps({
                'SourceDatabaseType': 'MySQL'
            }),
        })
        try:
            self.startApp()
        except:
            pass  # expected, this will fail due to MySQL

    def test_custom_runtime_setting_is_set(self):
        self.assert_string_in_recent_logs(
            self.app_name,
            'MySQL'
        )
