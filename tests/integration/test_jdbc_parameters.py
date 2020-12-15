import json

from tests.integration import basetest

# TODO check if we can unit test this
class TestJdbcParameters(basetest.BaseTestWithPostgreSQL):
    def test_default_jdbc_parameters(self):
        self.stage_container("BuildpackTestApp-mx-7-16.mda")
        self.start_container()
        self.assert_string_in_recent_logs("?tcpKeepAlive=true")

    def test_default_jdbc_parameters_7_23_1(self):
        self.stage_container("AdoptOpenJDKTest_7.23.1.mda")
        self.start_container()
        self.assert_string_in_recent_logs("?tcpKeepAlive=true")

    def test_overwrite_default(self):
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={
                "DATABASE_CONNECTION_PARAMS": json.dumps(
                    {"tcpKeepAlive": "false", "connectionTimeout": 30}
                )
            },
        )
        self.start_container()
        self.assert_string_in_recent_logs("tcpKeepAlive=false")
        self.assert_string_in_recent_logs("connectionTimeout=30")

    def test_invalid_jdbc_parameters(self):
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"DATABASE_CONNECTION_PARAMS": '{"tcpKeepAlive: "true"'},
        )
        self.start_container()
        self.assert_string_in_recent_logs(
            "Invalid JSON string for DATABASE_CONNECTION_PARAMS"
        )
