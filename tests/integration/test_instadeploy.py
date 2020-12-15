import backoff

from tests.integration import basetest


class TestCaseInstadeploy(basetest.BaseTest):
    def _test_instadeploy(self, mpk):
        self.stage_container(
            mpk,
            env_vars={
                "DEPLOY_PASSWORD": self._mx_password,
                "USE_DATA_SNAPSHOT": "false",
            },
        )
        self.start_container()

        @backoff.on_predicate(
            backoff.expo, lambda x: x.status_code > 501, max_time=180
        )
        def _await_mxbuild():
            return self.httpget(
                "/_mxbuild/", auth=("deploy", self._mx_password)
            )

        r = _await_mxbuild()
        if r.status_code > 501:
            raise Exception("Starting MxBuild takes too long")

        r = self.httppost(
            "/_mxbuild/",
            auth=("deploy", self._mx_password),
            files={"file": open(self._package_path, "rb")},
        )

        if r.status_code != 200:
            print(self.get_recent_logs())
            print(r.text)
        assert r.status_code == 200
        assert "STARTED" in r.text

    def test_instadeploy_7_18_3(self):
        self._test_instadeploy("ci-buildpack-test-app-mx7-18-3.mpk")
