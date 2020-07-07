import json

from tests.integration import basetest

BLOCK_ALL = "/widgets/GoogleMaps/"
BLOCK_ALL_BUT_SUB_PATH_WIDE_OPEN = "/widgets/GoogleMaps/widget/template/"
MY_IP_FILTER = "/widgets/GeoLocationForPhoneGap/"
OTHER_IP_FILTER = "/widgets/ProfileMenu/"
BASIC_AUTH = "/widgets/CameraWidgetForPhoneGap/widget/ui/"
BASIC_AUTH_AND_MY_IP_FILTER = "/styles/sass/lib/buildingblocks/"
BASIC_AUTH_AND_OTHER_IP_FILTER = "/styles/sass/lib/components/ "
BASIC_AUTH_OR_MY_IP_FILTER = "/styles/sass/lib/base/"
BASIC_AUTH_OR_OTHER_IP_FILTER = "/styles/sass/custom/pagetemplates/tablet/"

BLOCK_ALL_RESOURCE = BLOCK_ALL + "GoogleMaps.xml"
BLOCK_ALL_BUT_SUB_PATH_WIDE_OPEN_RESOURCE = (
    BLOCK_ALL_BUT_SUB_PATH_WIDE_OPEN + "GoogleMaps.html"
)
MY_IP_FILTER_RESOURCE = MY_IP_FILTER + "GeoLocationForPhoneGap.xml"
OTHER_IP_FILTER_RESOURCE = OTHER_IP_FILTER + "ProfileMenu.js"
BASIC_AUTH_RESOURCE = BASIC_AUTH + "CameraWidgetForPhoneGap.css"
BASIC_AUTH_AND_MY_IP_FILTER_RESOURCE = (
    BASIC_AUTH_AND_MY_IP_FILTER + "_wizard.scss"
)
BASIC_AUTH_AND_OTHER_IP_FILTER_RESOURCE = (
    BASIC_AUTH_AND_OTHER_IP_FILTER + "_alerts.scss"
)
BASIC_AUTH_OR_MY_IP_FILTER_RESOURCE = BASIC_AUTH_OR_MY_IP_FILTER + "_base.scss"
BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE = (
    BASIC_AUTH_OR_OTHER_IP_FILTER + "_tablet-page-wizard.scss"
)


class TestCaseAccessRestrictions(basetest.BaseTest):
    def test_access_is_restricted(self):
        myips = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
        wide_open_ips = ["0.0.0.0/0", "::/0"]
        other_ips = ["1.2.3.4/32", "1::2/128"]

        self.stage_container(
            "sample-6.2.0.mda",
            env_vars={
                "ACCESS_RESTRICTIONS": json.dumps(
                    {
                        BLOCK_ALL: {"ipfilter": []},
                        BLOCK_ALL_BUT_SUB_PATH_WIDE_OPEN: {
                            "ipfilter": wide_open_ips
                        },
                        MY_IP_FILTER: {"ipfilter": myips},
                        OTHER_IP_FILTER: {"ipfilter": other_ips},
                        BASIC_AUTH: {"basic_auth": {"user": "password"}},
                        BASIC_AUTH_AND_MY_IP_FILTER: {
                            "ipfilter": myips,
                            "basic_auth": {"user": "password"},
                            "satisfy": "all",
                        },
                        BASIC_AUTH_AND_OTHER_IP_FILTER: {
                            "ipfilter": other_ips,
                            "basic_auth": {"user": "password"},
                            "satisfy": "all",
                        },
                        BASIC_AUTH_OR_MY_IP_FILTER: {
                            "ipfilter": myips,
                            "basic_auth": {"user": "password"},
                            "satisfy": "any",
                        },
                        BASIC_AUTH_OR_OTHER_IP_FILTER: {
                            "ipfilter": other_ips,
                            "basic_auth": {"user": "password"},
                            "satisfy": "any",
                        },
                    }
                )
            },
        )
        self.start_container()

        auth = ("user", "password")
        auth_wrong_user = ("user1", "password")
        auth_wrong_pass = ("user", "password1")
        auth_wrong_pass2 = ("user", "somethingelse")

        success = all(
            [
                self._check_http_code(BLOCK_ALL_RESOURCE, 403),
                self._check_http_code(
                    BLOCK_ALL_BUT_SUB_PATH_WIDE_OPEN_RESOURCE, 200
                ),
                self._check_http_code(MY_IP_FILTER_RESOURCE, 200),
                self._check_http_code(OTHER_IP_FILTER_RESOURCE, 403),
                self._check_http_code(
                    OTHER_IP_FILTER_RESOURCE, 403, auth=auth
                ),
                self._check_http_code(BASIC_AUTH_RESOURCE, 200, auth=auth),
                self._check_http_code(BASIC_AUTH_RESOURCE, 401),
                self._check_http_code(
                    BASIC_AUTH_RESOURCE, 401, auth=auth_wrong_user
                ),
                self._check_http_code(
                    BASIC_AUTH_RESOURCE, 401, auth=auth_wrong_pass
                ),
                self._check_http_code(
                    BASIC_AUTH_RESOURCE, 401, auth=auth_wrong_pass2
                ),
                self._check_http_code(
                    BASIC_AUTH_AND_MY_IP_FILTER_RESOURCE, 200, auth=auth
                ),
                self._check_http_code(
                    BASIC_AUTH_AND_MY_IP_FILTER_RESOURCE, 401
                ),
                self._check_http_code(
                    BASIC_AUTH_AND_MY_IP_FILTER_RESOURCE,
                    401,
                    auth=auth_wrong_user,
                ),
                self._check_http_code(
                    BASIC_AUTH_AND_OTHER_IP_FILTER_RESOURCE, 403, auth=auth
                ),
                self._check_http_code(
                    BASIC_AUTH_OR_MY_IP_FILTER_RESOURCE, 200, auth=auth
                ),
                self._check_http_code(
                    BASIC_AUTH_OR_MY_IP_FILTER_RESOURCE, 200
                ),
                self._check_http_code(
                    BASIC_AUTH_OR_MY_IP_FILTER_RESOURCE,
                    200,
                    auth=auth_wrong_user,
                ),
                self._check_http_code(
                    BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE, 200, auth=auth
                ),
                self._check_http_code(
                    BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE,
                    401,
                    auth=auth_wrong_user,
                ),
                self._check_http_code(
                    BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE,
                    401,
                    auth=auth_wrong_pass,
                ),
                self._check_http_code(
                    BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE,
                    401,
                    auth=auth_wrong_pass2,
                ),
                self._check_http_code(
                    BASIC_AUTH_OR_OTHER_IP_FILTER_RESOURCE, 401
                ),
            ]
        )
        assert success

    def _check_http_code(self, path, expected_code, auth=None):
        r = self.httpget(path, auth=auth)
        if r.status_code == expected_code:
            print("OK")
        else:
            print(
                "NOK {} expected {} got {} authentication {}".format(
                    path, expected_code, r.status_code, auth
                )
            )
        return r.status_code == expected_code
