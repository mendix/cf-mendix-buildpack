import basetest
import buildpackutil
import os


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

        jdk = buildpackutil._determine_jdk("7.16.0")
        target_dir = buildpackutil._compose_jvm_target_dir(jdk)

        assert jdk["version"] == "8"
        assert target_dir == "usr/lib/jvm/jdk-8-oracle-x64"

        self._check_java_presence(target_dir)

    def test_adopt_jdk_8(self):
        self.setUpCF("AdoptOpenJDKTest_7.23.1.mda", health_timeout=60)
        self.startApp()

        jdk = buildpackutil._determine_jdk("7.23.1")
        target_dir = buildpackutil._compose_jvm_target_dir(jdk)

        assert jdk["version"] == "8u202"
        assert target_dir == "usr/lib/jvm/AdoptOpenJDK-8u202-AdoptOpenJDK-x64"

        self._check_java_presence(target_dir)
