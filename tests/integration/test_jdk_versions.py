import os

from buildpack.core import java, runtime
from tests.integration import basetest

CERT_TO_CHECK = "staat der nederlanden ev root ca"


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

    def test_adoptium_8(self):
        self._test_jdk(
            "AdoptOpenJDKTest_7.23.1.mda",
            "7.23.1",
            "8u332",
            "usr/lib/jvm/Adoptium-jre-8u332-Adoptium-x64",
        )

    def test_adoptium_11(self):
        self._test_jdk(
            "AdoptOpenJDKTest_8beta3.mda",
            "8.0.0",
            "11.0.15",
            "usr/lib/jvm/Adoptium-jre-11.0.15-Adoptium-x64",
        )

    def assert_certificate_in_cacert(self, cert_alias):
        result = self.run_on_container(
            "{} -list -storepass changeit -keystore {}".format(
                ".local/usr/lib/jvm/*/bin/keytool",
                ".local/usr/lib/jvm/*/lib/security/cacerts",
            ),
        )
        self.assertIn(cert_alias, result)
