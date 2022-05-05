import os

from buildpack.core import java
from tests.integration import basetest

CERT_TO_CHECK = "staat der nederlanden ev root ca"


class TestJDKVersions(basetest.BaseTest):
    def assert_java_presence(self, target_dir):
        assert self.is_present_in_container(
            os.path.join("/", target_dir)
        ) or self.is_present_in_container(
            os.path.join(".local", target_dir, "bin", "java")
        )

    def _test_jdk(
        self,
        mda,
        mx_version,
        jvm_version,
        check_certificate=True,
        override_version=None,
    ):
        env_vars = {}
        if override_version:
            env_vars = {java.JAVA_VERSION_OVERRIDE_KEY: override_version}
        self.stage_container(mda, env_vars=env_vars)

        variables = {}
        if override_version:
            variables = {"version": override_version}
        dependency = java._get_java_dependency(
            java.get_java_major_version(mx_version), "jre", variables=variables
        )

        target = java._compose_jvm_target_dir(dependency)

        assert dependency["version_key"] == jvm_version
        assert target == "usr/lib/jvm/%s-jre-%s-%s-x64" % (
            dependency["vendor"],
            dependency["version"],
            dependency["vendor"],
        )
        self.assert_java_presence(target)

        # TODO check if we can do this with staging / in one test only
        if check_certificate:
            self.start_container()
            self.assert_certificate_in_cacert(CERT_TO_CHECK)

    def test_adoptium_8(self):
        self._test_jdk("AdoptOpenJDKTest_7.23.1.mda", "7.23.1", "8")

    def test_adoptium_8_override(self):
        self._test_jdk(
            "AdoptOpenJDKTest_7.23.1.mda",
            "7.23.1",
            "8",
            check_certificate=False,
            override_version="8u322",
        )

    def test_adoptium_11(self):
        self._test_jdk("AdoptOpenJDKTest_8beta3.mda", "8.0.0", "11")

    def assert_certificate_in_cacert(self, cert_alias):
        result = self.run_on_container(
            "{} -list -storepass changeit -keystore {}".format(
                ".local/usr/lib/jvm/*/bin/keytool",
                ".local/usr/lib/jvm/*/lib/security/cacerts",
            ),
        )
        self.assertIn(cert_alias, result)
