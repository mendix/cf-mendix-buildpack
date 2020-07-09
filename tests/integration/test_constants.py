import json

from tests.integration import basetest

# TODO check if we can unit test this
class TestCaseConstants(basetest.BaseTest):
    def test_constant_is_set(self):
        self.stage_container(
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
        self.start_container()
        # this is enough because google.com would *always* respond
        self.assert_string_in_recent_logs(
            "java.net.ConnectException: Connection refused"
        )
