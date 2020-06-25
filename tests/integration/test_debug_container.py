from tests.integration import basetest


class TestCaseDebugContainer(basetest.BaseTest):
    def setUp(self):
        super().setUp()
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"DEBUG_CONTAINER": "true"},
        )
        self.start_container(status="unhealthy")

    def _assert_maintenance(self, response):
        assert response.status_code == 503
        assert "X-Mendix-Cloud-Mode" in response.headers
        assert response.headers["X-Mendix-Cloud-Mode"] == "maintenance"
        assert "App is in maintenance mode" in response.text

    def test_maintenance_get(self):
        r = self.httpget("/index.html")
        self._assert_maintenance(r)

    def test_maintenance_post(self):
        r = self.httpget("/xas/")
        self._assert_maintenance(r)
