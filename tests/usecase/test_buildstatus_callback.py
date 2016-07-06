import os
import subprocess
import basetest


class TestCaseBuildStatusCallback(basetest.BaseTest):

    def test_model_has_inconsistency_errors(self):
        package_name = "broken-6-build7751.mpk"
        self._test_helper(package_name)
        try:
            subprocess.check_call("cf start \"%s\"" % self.app_name, shell=True)
        except subprocess.CalledProcessError:
            logs_out = subprocess.check_output("cf logs \"%s\" --recent" % self.app_name, shell=True)
            print(logs_out)
            assert 'Submitting build status' in logs_out

    def test_model_has_no_inconsistency_errors(self):
        package_name = "sample-6.2.0.mpk"
        self._test_helper(package_name)
        subprocess.check_call("cf start \"%s\"" % self.app_name, shell=True)
        self.assert_app_running(self.app_name)

    def _test_helper(self, package_name):
        runtimes_base_url = os.environ.get("RUNTIMES_BASE_URL")
        runtime_url = "{base}/mendix-6-build10037.tar.gz".format(base=runtimes_base_url)
        mxbuild_url = "{base}/mxbuild-6-build10037.tar.gz".format(base=runtimes_base_url)
        self.setUpCF(package_name)

        cmds = [
            "cf set-env \"%s\" FORCED_MXBUILD_URL \"%s\"" % (self.app_name, mxbuild_url),
            "cf set-env \"%s\" FORCED_MXRUNTIME_URL \"%s\"" % (self.app_name, runtime_url),
            "cf set-env \"%s\" FORCE_WRITE_BUILD_ERRORS \"true\"" % self.app_name,
            "cf set-env \"%s\" BUILD_STATUS_CALLBACK_URL \"http://localhost/buildstatus\"" % self.app_name
        ]
        for cmd in cmds:
            subprocess.check_call(cmd, shell=True)
