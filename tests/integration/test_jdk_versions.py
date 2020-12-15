import os

from buildpack import java, runtime
from tests.integration import basetest

CERT_TO_CHECK = "staat der nederlanden root ca - g3"


class TestJDKVersions(basetest.BaseTest):
    def assert_java_presence(self, target_dir):
        assert self.is_present_in_container(
            os.path.join("/", target_dir)
        ) or self.is_present_in_container(
            os.path.join(".local", target_dir, "bin", "java")
        )

    def _test_jdk(self, mda, mx_version, jdk_version, target_dir):
        self.stage_container(mda)

        jdk = java.determine_jdk(runtime.get_java_version(mx_version), "jre")
        target = java.compose_jvm_target_dir(jdk)

        assert jdk["version"] == jdk_version
        assert target == target_dir
        self.assert_java_presence(target)

        # TODO check if we can do this with staging / in one test only
        self.start_container()
        self.assert_certificate_in_cacert(CERT_TO_CHECK)

    def test_oracle_jdk_8(self):
        self._test_jdk(
            "BuildpackTestApp-mx-7-16.mda",
            "7.16.0",
            "8u261",
            "usr/lib/jvm/jre-8u261-oracle-x64",
        )

    def test_adopt_jdk_8(self):
        self._test_jdk(
            "AdoptOpenJDKTest_7.23.1.mda",
            "7.23.1",
            "8u262",
            "usr/lib/jvm/AdoptOpenJDK-jre-8u262-AdoptOpenJDK-x64",
        )

    def test_adopt_jdk_11(self):
        self._test_jdk(
            "AdoptOpenJDKTest_8beta3.mda",
            "8.0.0",
            "11.0.8",
            "usr/lib/jvm/AdoptOpenJDK-jre-11.0.8-AdoptOpenJDK-x64",
        )

    def assert_certificate_in_cacert(self, cert_alias):
        result = self.run_on_container(
            "{} -list -storepass changeit -keystore {}".format(
                ".local/usr/lib/jvm/*/bin/keytool",
                ".local/usr/lib/jvm/*/lib/security/cacerts",
            ),
        )
        self.assertIn(cert_alias, result)
