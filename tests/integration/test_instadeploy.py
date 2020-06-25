import os

import backoff

from buildpack import java, runtime
from tests.integration import basetest


class TestCaseInstadeploy(basetest.BaseTest):
    def assert_java_presence(self, target_dir):
        try:
            self.run_on_container(
                "{} -version".format(os.path.join("/", target_dir))
            )
            rootCheckFail = False
        except RuntimeError:
            rootCheckFail = True

        try:
            self.run_on_container(
                "{} -version".format(
                    os.path.join(".local", target_dir, "bin", "java")
                )
            )
            localCheckFail = False
        except RuntimeError:
            localCheckFail = True

        assert not (rootCheckFail and localCheckFail)

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

    # TODO check if we really need to do this test
    def test_instadeploy_7_23_1_java_present(self):
        self._test_instadeploy("AdoptOpenJDKTest_7.23.1.mpk")

        jdk = java.determine_jdk(runtime.get_java_version("7.23.1"))
        target_dir = java.compose_jvm_target_dir(jdk)

        assert jdk["version"] == "8u202"
        assert (
            target_dir == "usr/lib/jvm/AdoptOpenJDK-jdk-8u202-AdoptOpenJDK-x64"
        )

        self.assert_java_presence(target_dir)
