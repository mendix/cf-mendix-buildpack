import os
import subprocess
import basetest


class TestCaseBuildStatusCallback(basetest.BaseTest):
    def setUp(self):
        runtimes_base_url = os.environ.get("RUNTIMES_BASE_URL")

        runtime_url = "{base}/mendix-6-build7751.tar.gz".format(base=runtimes_base_url)
        mxbuild_url = "{base}/mxbuild-6-build7751.tar.gz".format(base=runtimes_base_url)
        package_name = "broken-6-build7751.mpk"

        self.setUpCF(package_name)

        cmds = [
            "cf set-env \"%s\" FORCED_MXBUILD_URL \"%s\"" % (self.app_name, mxbuild_url),
            "cf set-env \"%s\" FORCED_MXRUNTIME_URL \"%s\"" % (self.app_name, runtime_url),
            "cf set-env \"%s\" FORCE_WRITE_BUILD_ERRORS \"true\"" % self.app_name,
            "cf set-env \"%s\" BUILD_STATUS_CALLBACK_URL \"http://localhost/buildstatus\"" % self.app_name
        ]
        for cmd in cmds:
            subprocess.check_call(cmd, shell=True)

    def test_model_has_inconsistency_errors(self):
        try:
            subprocess.check_call("cf start \"%s\"" % self.app_name, shell=True)
        except subprocess.CalledProcessError:
            logs_out = subprocess.check_output("cf logs \"%s\" --recent" % self.app_name, shell=True)
            print(logs_out)
            assert 'Submitting build status' in logs_out
