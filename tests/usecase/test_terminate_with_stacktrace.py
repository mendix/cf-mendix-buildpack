import basetest


class TestCaseTerminateWithStacktrace(basetest.BaseTest):
    """
    Tests that the process terminates with a stack trace when Python code
    errors. The env variable S3_ENCRYPTION_KEYS is used here, it doesn't
    have a try-except on it.
    """

    def setUp(self):
        super().setUp()
        self.setUpCF(
            "Mendix8.1.1.58432_StarterApp.mda",
            env_vars={"S3_ENCRYPTION_KEYS": "{invalid-json}"},
        )

    def test_verify_termination_logs(self):
        self.startApp(expect_failure=True)
        self.assert_string_in_recent_logs(
            'json.loads(os.getenv("S3_ENCRYPTION_KEYS"))'
        )
