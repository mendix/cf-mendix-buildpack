import json

from tests.integration import basetest


class TestCaseMpkAppDeployed(basetest.BaseTest):
    def test_model_has_inconsistency_errors(self):
        with self.assertRaises(RuntimeError):
            self.stage_container(
                "model-with-consistency-errors-7.0.2.mpk",
                env_vars={"FORCE_WRITE_BUILD_ERRORS": "true",},
            )

    def test_model_has_no_inconsistency_errors(self):
        assert self.stage_container("empty-model-7.0.2.mpk")

    def test_mpk_app_deployed_unauthorized(self):
        self.stage_container("MontBlancApp720.mpk")
        self.start_container()
        self.assert_app_running()

    # TODO determine if we need this test
    def test_mpk_app_deploys_can_log_in(self):
        self.stage_container(
            "MontBlancApp720WithSampleData.mpk", use_snapshot=True
        )
        self.start_container()

        login_action = {
            "action": "login",
            "params": {"username": "henk", "password": "henkie"},
        }

        r = self.httppost(
            "/xas/",
            headers={"Content-Type": "application/json"},
            data=json.dumps(login_action),
        )

        assert r.status_code == 200
