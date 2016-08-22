import subprocess
import basetest
import time


class TestCaseEmitMetrics(basetest.BaseTest):

    def setUp(self):
        package_name = "sample-6.2.0.mda"
        self.setUpCF(package_name)
        subprocess.check_call("cf set-env \"%s\" METRICS_INTERVAL 10" % self.app_name, shell=True)
        subprocess.check_call("cf start \"%s\"" % self.app_name, shell=True)

    def test_read_metrics_in_logs(self):
        time.sleep(10)
        output = subprocess.check_output("cf logs \"%s\" --recent" % self.app_name, shell=True)
        print output
        if output.find('MENDIX-METRICS: ') > 0:
            pass
        else:
            self.fail("conditions not met")
