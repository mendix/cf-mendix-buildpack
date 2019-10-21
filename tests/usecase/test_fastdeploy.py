import basetest
import requests
import time


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
        self.cmd(
            (
                "wget",
                "--quiet",
                "https://s3-eu-west-1.amazonaws.com"
                "/mx-buildpack-ci/ci-buildpack-test-app-mx7-18-3.mpk",
            )
        )
        full_uri = "https://" + self.app_name + "/_mxbuild/"

        max = 12
        for attempt in range(0, max):
            time.sleep(10)
            r = requests.get(full_uri, auth=("deploy", self.mx_password))
            if r.status_code == 501:
                break
            if attempt == max - 1:
                raise Exception("Starting MxBuild takes too long")

        # making sure mxbuild is ready
        time.sleep(10)

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
