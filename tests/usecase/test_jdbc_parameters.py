import basetest
import json


class TestJdbcParameters(basetest.BaseTest):
    def setUp(self):
        super().setUp()

    def test_default_jdbc_parameters(self):
        self.setUpCF("BuildpackTestApp-mx-7-16.mda", health_timeout=60)
        self.startApp()
        self.assert_string_in_recent_logs("?tcpKeepAlive=true")

    def test_default_jdbc_parameters_7_23_1(self):
        self.setUpCF("AdoptOpenJDKTest_7.23.1.mda", health_timeout=60)
        self.startApp()
        self.assert_string_in_recent_logs("?tcpKeepAlive=true")

    def test_overwrite_default(self):
        self.setUpCF(
            "BuildpackTestApp-mx-7-16.mda",
            health_timeout=60,
            env_vars={
                "DATABASE_CONNECTION_PARAMS": json.dumps(
                    {"tcpKeepAlive": "false", "connectionTimeout": 30}
                )
            },
        )
        self.startApp()
        self.assert_string_in_recent_logs("tcpKeepAlive=false")
        self.assert_string_in_recent_logs("connectionTimeout=30")

    def test_invalid_jdbc_parameters(self):
        self.setUpCF(
            "BuildpackTestApp-mx-7-16.mda",
            health_timeout=60,
            env_vars={"DATABASE_CONNECTION_PARAMS": '{"tcpKeepAlive: "true"}'},
        )
        self.startApp()
        self.assert_string_in_recent_logs(
            "Invalid JSON string for DATABASE_CONNECTION_PARAMS"
        )
