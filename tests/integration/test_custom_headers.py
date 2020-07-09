import json

from tests.integration import basetest


class TestCaseCustomHeaders(basetest.BaseTest):
    def test_custom_headers(self):
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={
                "X_FRAME_OPTIONS": "DENY",
                "HTTP_RESPONSE_HEADERS": json.dumps(
                    {
                        "X-Permitted-Cross-Domain-Policies": "by-content-type",
                        "Access-Control-Allow-Origin": "https://this.is.mydomain.nl",
                        "X-XSS-Protection": "1; report=https://domainwithnewstyle.tld.consultancy",
                        "X-Content-Type-Options": "nosniff",
                    }
                ),
            },
        )
        self.start_container()

        self.assert_app_running()
        response = self.httpget()
        self.assertIn("DENY", response.headers["X-Frame-Options"])
        self.assertIn(
            "https://this.is.mydomain.nl",
            response.headers["Access-Control-Allow-Origin"],
        )
        self.assertIn("nosniff", response.headers["X-Content-Type-Options"])
        self.assertIn(
            "by-content-type",
            response.headers["X-Permitted-Cross-Domain-Policies"],
        )
        self.assertIn(
            "1; report=https://domainwithnewstyle.tld.consultancy",
            response.headers["X-XSS-Protection"],
        )
