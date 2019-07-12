import basetest
import json


class TestCaseConstants(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "sample-6.2.0.mda",
            env_vars={
                # has more precedence
                "MX_AppCloudServices_OpenIdProvider": "http://localhost",
                # over this one
                "CONSTANTS": json.dumps(
                    {
                        "AppCloudServices.OpenIdEnabled": True,
                        "AppCloudServices.OpenIdProvider": "http://google.com/",
                    }
                ),
            },
        )
        self.startApp()

    def test_constant_is_set(self):
        # this is enough because google.com would *always* respond
        self.assert_string_in_recent_logs(
            "java.net.ConnectException: Connection refused"
        )
