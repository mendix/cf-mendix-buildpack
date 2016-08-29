import basetest
import subprocess
import requests
import json


class TestCaseSampleData(basetest.BaseTest):
    _multiprocess_can_split_ = True

    def setUp(self):
        self.setUpCF('MontBlancApp671WithSampleData.mpk')
        subprocess.check_call(('cf', 'start', self.app_name))

    def test_user_from_sampledata_can_log_in(self):
        full_uri = "https://" + self.app_name + "/xas/"
        login_action = {
            'action': 'login',
            'params': {
                'username': 'henk',
                'password': 'henkie',
            },
        }
        r = requests.post(
            full_uri,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(login_action),
        )
        assert r.status_code == 200
