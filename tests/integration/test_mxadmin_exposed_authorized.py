from tests.integration import basetest


# TODO check if we should test this (MxAdmin is implicit in app startup)
class TestCaseMxAdminExposed(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.stage_container("BuildpackTestApp-mx-7-16.mda")
        self.start_container()

    def test_mxadmin_exposed_unauthorized(self):
        r = self.httpget("/_mxadmin/")
        assert r.status_code == 401

    def test_mxadmin_exposed_authorized(self):
        r = self.httpget("/_mxadmin/", auth=("MxAdmin", self._mx_password))
        assert r.status_code == 200
