import unittest
import os
import start
import json


class TestCaseCustomHeaderConfig(unittest.TestCase):
    def test_valid_header_xfrmaeOption(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Frame-Options": "allow-from https://mendix.com"}
        )
        os.environ["X_FRAME_OPTIONS"] = "deny"
        header_config = start.parse_headers()
        self.assertIn(
            "add_header X-Frame-Options 'allow-from https://mendix.com';",
            header_config,
        )

    def test_invalid_header_xframeOption(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Frame-Options": "allow-form htps://mendix.com"}
        )
        header_config = start.parse_headers()
        self.assertEquals("", header_config)

    def test_valid_with_xframeOption(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = "{}"
        os.environ["X_FRAME_OPTIONS"] = "DENY"
        header_config = start.parse_headers()
        self.assertIn("add_header X-Frame-Options 'DENY';", header_config)

    def test_valid_header_referrerPolicy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"Referrer-Policy": "no-referrer-when-downgrade"}
        )
        header_config = start.parse_headers()
        self.assertIn(
            "add_header Referrer-Policy 'no-referrer-when-downgrade';",
            header_config,
        )

    def test_invalid_header_referrerPolicy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"Referrer-Policy": "no-referrr-when-downgrade"}
        )
        header_config = start.parse_headers()
        self.assertEquals("", header_config)

    def test_valid_header_accessControl(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"Access-Control-Allow-Origin": "*"}
        )
        header_config = start.parse_headers()
        self.assertIn(
            "add_header Access-Control-Allow-Origin '*';", header_config
        )

    def test_invalid_header_accessControl(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"Access-Control-Allow-Origin": "htps://this.is.mydomain.nl"}
        )
        header_config = start.parse_headers()
        self.assertEquals("", header_config)

    def test_valid_header_contentType(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Content-Type-Options": "nosniff"}
        )
        header_config = start.parse_headers()
        self.assertIn(
            "add_header X-Content-Type-Options 'nosniff';", header_config
        )

    def test_invalid_header_contentType(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Content-Type-Options": ""}
        )
        header_config = start.parse_headers()
        self.assertEquals("", header_config)

    def test_valid_header_contentSecurity(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Content-Security-Policy": "default-src https: \u0027unsafe-eval\u0027 \u0027unsafe-inline\u0027; object-src \u0027none\u0027"  # noqa: E501
            }
        )
        header_config = start.parse_headers()
        self.assertIn(
            "add_header Content-Security-Policy 'default-src https: \\'unsafe-eval\\' \\'unsafe-inline\\'; object-src \\'none\\'';",  # noqa: E501
            header_config,
        )

    def test_invalid_header_contentSecurity(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Content-Security-Policy": "$# default-src https://my.csp.domain.amsterdam"
            }
        )
        header_config = start.parse_headers()
        self.assertEquals("", header_config)

    def test_valid_header_permittedPolicies(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Permitted-Cross-Domain-Policies": "by-content-type"}
        )
        header_config = start.parse_headers()
        self.assertIn(
            "add_header X-Permitted-Cross-Domain-Policies 'by-content-type';",
            header_config,
        )

    def test_invalid_header_permittedPolicies(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Permitted-Cross-Domain-Policies": "#%#^#^"}
        )
        header_config = start.parse_headers()
        self.assertEquals("", header_config)

    def test_valid_header_xssProtection(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "X-XSS-Protection": "1; report=https://domainwithnewstyle.tld.consultancy"
            }
        )
        header_config = start.parse_headers()
        self.assertIn(
            "add_header X-XSS-Protection '1; report=https://domainwithnewstyle.tld.consultancy';",
            header_config,
        )

    def test_invalid_header_xssProtection(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-XSS-Protection": "1;mode=bock"}
        )
        header_config = start.parse_headers()
        self.assertEquals("", header_config)

    def test_valid_header_partial(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Referrer-Policy": "no-referrr-when-downgrade",
                "Access-Control-Allow-Origin": "https://this.is.mydomain.nl",
                "X-Content-Type-Options": "nosniff",
            }
        )
        header_config = start.parse_headers()
        self.assertNotIn(
            "add_header X-XSS-Protection '1; report=https://domainwithnewstyle.tld.consultancy';",
            header_config,
        )

    def test_invalid_header_json(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = "invalid"
        try:
            start.parse_headers()
        except json.JSONDecodeError as e:
            pass
