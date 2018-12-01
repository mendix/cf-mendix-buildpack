import subprocess
import basetest


class TestCaseBuildStatusCallback(basetest.BaseTest):
    def test_model_has_inconsistency_errors(self):
        self._test_helper("model-with-consistency-errors-7.0.2.mpk")
        try:
            self.startApp()
        except subprocess.CalledProcessError:
            logs_out = self.cmd(("cf", "logs", self.app_name, "--recent"))
            print(logs_out)
            assert "Submitting build status" in logs_out

    def test_model_has_no_inconsistency_errors(self):
        self._test_helper("empty-model-7.0.2.mpk")
        self.startApp()
        self.assert_app_running()

    def _test_helper(self, package_name):
        self.setUpCF(
            package_name,
            env_vars={
                "FORCE_WRITE_BUILD_ERRORS": "true",
                "BUILD_STATUS_CALLBACK_URL": "http://localhost/buildstatus",
            },
        )
