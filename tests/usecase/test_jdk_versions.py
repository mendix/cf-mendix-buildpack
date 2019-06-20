import basetest
import buildpackutil
import os
import requests
import time


class TestJDKVersions(basetest.BaseTest):
    def setUp(self):
        super().setUp()

    def _check_java_presence(self, target_dir):

        try:
            self.cmd(
                (
                    "cf",
                    "ssh",
                    self.app_name,
                    "-c",
                    os.path.join("/{}".format(target_dir), "bin", "java")
                    + " -version",
                )
            )
            rootCheckFail = False
        except Exception:
            rootCheckFail = True

        try:
            self.cmd(
                (
                    "cf",
                    "ssh",
                    self.app_name,
                    "-c",
                    os.path.join(
                        "/home/vcap/app/.local/{}".format(target_dir),
                        "bin",
                        "java",
                    )
                    + " -version",
                )
            )
            localCheckFail = False
        except Exception:
            localCheckFail = True

        assert not (rootCheckFail and localCheckFail)

    def test_oracle_jdk_8(self):
        self.setUpCF("BuildpackTestApp-mx-7-16.mda", health_timeout=60)
        self.startApp()

        jdk = buildpackutil._determine_jdk("7.16.0", "jre")
        target_dir = buildpackutil._compose_jvm_target_dir(jdk)

        assert jdk["version"] == "8u202"
        assert target_dir == "usr/lib/jvm/jre-8u202-oracle-x64"

        self._check_java_presence(target_dir)
        self.assert_certificate_in_cacert("staat der nederlanden root ca - g3")

    def test_adopt_jdk_8(self):
        self.setUpCF("AdoptOpenJDKTest_7.23.1.mda", health_timeout=60)
        self.startApp()

        jdk = buildpackutil._determine_jdk("7.23.1", "jre")
        target_dir = buildpackutil._compose_jvm_target_dir(jdk)

        assert jdk["version"] == "8u202"
        assert (
            target_dir == "usr/lib/jvm/AdoptOpenJDK-jre-8u202-AdoptOpenJDK-x64"
        )

        self._check_java_presence(target_dir)
        self.assert_certificate_in_cacert("staat der nederlanden root ca - g3")

    def test_adopt_jdk_11(self):
        self.setUpCF("AdoptOpenJDKTest_8beta3.mda", health_timeout=60)
        self.startApp()

        jdk = buildpackutil._determine_jdk("8.0.0", "jre")
        target_dir = buildpackutil._compose_jvm_target_dir(jdk)

        assert jdk["version"] == "11.0.3"
        assert (
            target_dir
            == "usr/lib/jvm/AdoptOpenJDK-jre-11.0.3-AdoptOpenJDK-x64"
        )
        self._check_java_presence(target_dir)
        self.assert_certificate_in_cacert("staat der nederlanden root ca - g3")

    def test_fast_deploy_7_23_1(self):
        self.setUpCF(
            "AdoptOpenJDKTest_7.23.1.mpk",
            env_vars={"DEPLOY_PASSWORD": self.mx_password},
        )
        self.startApp()

        self.cmd(
            (
                "wget",
                "--quiet",
                "https://s3-eu-west-1.amazonaws.com"
                "/mx-buildpack-ci/AdoptOpenJDKTest_7.23.1.mpk",
            )
        )
        full_uri = "https://" + self.app_name + "/_mxbuild/"
        time.sleep(60)
        r = requests.post(
            full_uri,
            auth=("deploy", self.mx_password),
            files={"file": open("AdoptOpenJDKTest_7.23.1.mpk", "rb")},
        )

        if r.status_code != 200:
            print(self.get_recent_logs())
            print(r.text)
        assert r.status_code == 200
        assert "STARTED" in r.text

        jdk = buildpackutil._determine_jdk("7.23.1")
        target_dir = buildpackutil._compose_jvm_target_dir(jdk)

        assert jdk["version"] == "8u202"
        assert (
            target_dir == "usr/lib/jvm/AdoptOpenJDK-jdk-8u202-AdoptOpenJDK-x64"
        )

        self._check_java_presence(target_dir)
