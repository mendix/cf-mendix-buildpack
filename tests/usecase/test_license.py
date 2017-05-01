import subprocess
import basetest


class TestLicense(basetest.BaseTest):

    def setUp(self):
        self.setUpCF('sample-6.2.0.mda')
        subprocess.check_call((
            'cf', 'set-env', self.app_name,
            'LICENSE_ID',
            'dead-beef'
        ))
        subprocess.check_call((
            'cf', 'set-env', self.app_name,
            'LICENSE_KEY',
            'Base64'
        ))
        self.startApp()

    def test_license_is_detected(self):
        self.assert_string_in_recent_logs(
            self.app_name,
            'Error processing license key. Please check if you have submitted the full Mendix license key. Key verification failed (10010). The key is not in a valid format'
        )
