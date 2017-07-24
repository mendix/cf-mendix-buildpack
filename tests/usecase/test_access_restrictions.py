import basetest
import requests
import json


BLOCK_ALL = '/widgets/GoogleMaps/'
BLOCK_ALL_BUT_SUB_PATH_WIDE_OPEN = '/widgets/GoogleMaps/widget/template/'
MY_IP_FILTER = '/widgets/GeoLocationForPhoneGap/'
OTHER_IP_FILTER = '/widgets/ProfileMenu/'
BASIC_AUTH = '/widgets/CameraWidgetForPhoneGap/widget/ui/'
BASIC_AUTH_AND_MY_IP_FILTER = '/styles/sass/lib/buildingblocks/'
BASIC_AUTH_AND_OTHER_IP_FILTER = '/styles/sass/lib/components/ '
BASIC_AUTH_OR_MY_IP_FILTER = '/styles/sass/lib/base/'
BASIC_AUTH_OR_OTHER_IP_FILTER = '/styles/sass/custom/pagetemplates/tablet/'

BLOCK_ALL_RESOURCE = BLOCK_ALL + 'GoogleMaps.xml'
BLOCK_ALL_BUT_SUB_PATH_WIDE_OPEN_RESOURCE = BLOCK_ALL_BUT_SUB_PATH_WIDE_OPEN + 'GoogleMaps.html'
MY_IP_FILTER_RESOURCE = MY_IP_FILTER + 'GeoLocationForPhoneGap.xml'
OTHER_IP_FILTER_RESOURCE = OTHER_IP_FILTER + 'ProfileMenu.js'
BASIC_AUTH_RESOURCE = BASIC_AUTH + 'CameraWidgetForPhoneGap.css'
BASIC_AUTH_AND_MY_IP_FILTER_RESOURCE = BASIC_AUTH_AND_MY_IP_FILTER + '_wizard.scss'
BASIC_AUTH_AND_OTHER_IP_FILTER_RESOURCE = BASIC_AUTH_AND_OTHER_IP_FILTER + '_alerts.scss'
BASIC_AUTH_OR_MY_IP_FILTER_RESOURCE = BASIC_AUTH_OR_MY_IP_FILTER + '_base.scss'
BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE = BASIC_AUTH_OR_OTHER_IP_FILTER + '_tablet-page-wizard.scss'


class TestCaseAccessRestrictions(basetest.BaseTest):

    def setUp(self):
        myips = []
        wide_open_ips = ['0.0.0.0/0']
        other_ips = ['1.2.3.4/32']

        r = requests.get('https://myipv4.mendix.com/', timeout=5)
        r.raise_for_status()
        myips.append(r.text.strip() + '/32')

        # IPv6 does not work currently, we use nginx compiled by staticfile
        # buildpack. We copy it to our CDN when it is available.
        # There is an issue open for --with-ipv6 support:
        # https://github.com/cloudfoundry/staticfile-buildpack/issues/109

        # wide_open_ips.append('::/0')
        # try:
        #     myips.append(requests.get('https://myipv6.mendix.com/').text + '/128')
        # except:
        #     pass

        print('my ip ranges are', ','.join(myips))

        self.setUpCF('sample-6.2.0.mda', env_vars={
            'ACCESS_RESTRICTIONS': json.dumps({
                BLOCK_ALL: {'ipfilter': []},
                BLOCK_ALL_BUT_SUB_PATH_WIDE_OPEN: {'ipfilter': wide_open_ips},
                MY_IP_FILTER: {'ipfilter': myips},
                OTHER_IP_FILTER: {'ipfilter': other_ips},
                BASIC_AUTH: {'basic_auth': {'user': 'password'}},
                BASIC_AUTH_AND_MY_IP_FILTER: {
                    'ipfilter': myips,
                    'basic_auth': {'user': 'password'},
                    'satisfy': 'all',
                },
                BASIC_AUTH_AND_OTHER_IP_FILTER: {
                    'ipfilter': other_ips,
                    'basic_auth': {'user': 'password'},
                    'satisfy': 'all',
                },
                BASIC_AUTH_OR_MY_IP_FILTER: {
                    'ipfilter': myips,
                    'basic_auth': {'user': 'password'},
                    'satisfy': 'any',
                },
                BASIC_AUTH_OR_OTHER_IP_FILTER: {
                    'ipfilter': other_ips,
                    'basic_auth': {'user': 'password'},
                    'satisfy': 'any',
                },
            })
        })
        self.startApp()

    def test_access_is_restricted(self):
        auth = ('user', 'password')
        auth_wrong_user = ('user1', 'password')
        auth_wrong_pass = ('user', 'password1')
        auth_wrong_pass2 = ('user', 'somethingelse')

        success = all([
            self._httpget(BLOCK_ALL_RESOURCE, 403),

            self._httpget(BLOCK_ALL_BUT_SUB_PATH_WIDE_OPEN_RESOURCE, 200),

            self._httpget(MY_IP_FILTER_RESOURCE, 200),

            self._httpget(OTHER_IP_FILTER_RESOURCE, 403),
            self._httpget(OTHER_IP_FILTER_RESOURCE, 403, auth=auth),

            self._httpget(BASIC_AUTH_RESOURCE, 200, auth=auth),
            self._httpget(BASIC_AUTH_RESOURCE, 401),
            self._httpget(BASIC_AUTH_RESOURCE, 401, auth=auth_wrong_user),
            self._httpget(BASIC_AUTH_RESOURCE, 401, auth=auth_wrong_pass),
            self._httpget(BASIC_AUTH_RESOURCE, 401, auth=auth_wrong_pass2),

            self._httpget(BASIC_AUTH_AND_MY_IP_FILTER_RESOURCE, 200, auth=auth),
            self._httpget(BASIC_AUTH_AND_MY_IP_FILTER_RESOURCE, 401),
            self._httpget(BASIC_AUTH_AND_MY_IP_FILTER_RESOURCE, 401, auth=auth_wrong_user),

            self._httpget(BASIC_AUTH_AND_OTHER_IP_FILTER_RESOURCE, 403, auth=auth),

            self._httpget(BASIC_AUTH_OR_MY_IP_FILTER_RESOURCE, 200, auth=auth),
            self._httpget(BASIC_AUTH_OR_MY_IP_FILTER_RESOURCE, 200),
            self._httpget(BASIC_AUTH_OR_MY_IP_FILTER_RESOURCE, 200, auth=auth_wrong_user),

            self._httpget(BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE, 200, auth=auth),
            self._httpget(BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE, 401, auth=auth_wrong_user),
            self._httpget(BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE, 401, auth=auth_wrong_pass),
            self._httpget(BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE, 401, auth=auth_wrong_pass2),
            self._httpget(BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE, 401),
        ])
        assert success

    def _httpget(self, path, expected_code, auth=None):
        r = requests.get('https://' + self.app_name + path, auth=auth)
        print('OK' if r.status_code == expected_code else 'NOK', path, 'expected', expected_code, 'got', r.status_code, 'authentication', auth)
        return r.status_code == expected_code
