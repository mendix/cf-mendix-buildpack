import os

from buildpack.core import java
from tests.integration import basetest


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

    def test_adoptium_8(self):
        self._test_jdk("AdoptOpenJDKTest_7.23.1.mda", "7.23.1", "8")

    def test_adoptium_8_override(self):
        self._test_jdk(
            "AdoptOpenJDKTest_7.23.1.mda",
            "7.23.1",
            "8",
            override_version="8u322",
        )

    def test_adoptium_11(self):
        self._test_jdk("AdoptOpenJDKTest_8beta3.mda", "8.0.0", "11")
