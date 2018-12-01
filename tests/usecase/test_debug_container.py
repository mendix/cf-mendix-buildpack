import basetest
import requests


class TestCaseDebugContainer(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.setUpCF(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"DEBUG_CONTAINER": "true"},
        )
        self.startApp()

    def _assert_maintenance(self, response):
        assert response.status_code == 503
        assert "X-Mendix-Cloud-Mode" in response.headers
        assert response.headers["X-Mendix-Cloud-Mode"] == "maintenance"
        assert "App is in maintenance mode" in response.text

    def test_maintenance_mode(self):
        self.assert_app_running(code=503)
        self.assert_string_in_recent_logs("App is in maintenance mode")

    def test_maintenance_get(self):
        full_uri = "https://" + self.app_name + "/index.html"
        r = requests.get(full_uri)
        self._assert_maintenance(r)

    def test_maintenance_post(self):
        full_uri = "https://" + self.app_name + "/xas/"
        r = requests.get(full_uri)
        self._assert_maintenance(r)
