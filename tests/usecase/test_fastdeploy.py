import basetest
import requests
import time


class TestCaseFastdeploy(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "MontBlancApp720.mpk",
            env_vars={"DEPLOY_PASSWORD": self.mx_password},
        )
        self.startApp()

    def test_fast_deploy(self):
        self.cmd(
            (
                "wget",
                "--quiet",
                "https://s3-eu-west-1.amazonaws.com"
                "/mx-buildpack-ci/MontBlancApp720b.mpk",
            )
        )
        full_uri = "https://" + self.app_name + "/_mxbuild/"
        time.sleep(10)
        r = requests.post(
            full_uri,
            auth=("deploy", self.mx_password),
            files={"file": open("MontBlancApp720b.mpk", "rb")},
        )

        if r.status_code != 200:
            print(self.get_recent_logs())
            print(r.text)
        assert r.status_code == 200
        assert "STARTED" in r.text
