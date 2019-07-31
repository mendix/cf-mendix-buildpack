import basetest
import requests


class TestCaseFastdeploy(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "ci-buildpack-test-app-mx7-18-3.mpk",
            env_vars={
                "DEPLOY_PASSWORD": self.mx_password,
                "USE_DATA_SNAPSHOT": "false",
            },
        )
        self.startApp()

    def test_fast_deploy(self):
        self.wait_for_mxbuild()

        self.cmd(
            (
                "wget",
                "--quiet",
                "https://s3-eu-west-1.amazonaws.com"
                "/mx-buildpack-ci/ci-buildpack-test-app-mx7-18-3.mpk",
            )
        )

        full_uri = "https://" + self.app_name + "/_mxbuild/"
        r = requests.post(
            full_uri,
            auth=("deploy", self.mx_password),
            files={"file": open("ci-buildpack-test-app-mx7-18-3.mpk", "rb")},
        )

        if r.status_code != 200:
            print(self.get_recent_logs())
            print(r.text)
        assert r.status_code == 200
        assert "STARTED" in r.text
