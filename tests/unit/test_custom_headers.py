import json
import os
import unittest

from buildpack.core import nginx


class TestCaseCustomHeaderConfig(unittest.TestCase):
    def test_valid_header_xfrmaeOption(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Frame-Options": "allow-from https://mendix.com"}
        )
        os.environ["X_FRAME_OPTIONS"] = "deny"
        header_config = nginx._get_http_headers()
        self.assertIn(
            ("X-Frame-Options", "allow-from https://mendix.com"),
            header_config,
        )

    def test_invalid_header_xframeOption(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Frame-Options": "allow-form htps://mendix.com"}
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_with_xframeOption(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = "{}"
        os.environ["X_FRAME_OPTIONS"] = "DENY"
        header_config = nginx._get_http_headers()
        self.assertIn(("X-Frame-Options", "DENY"), header_config)

    def test_valid_header_referrerPolicy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"Referrer-Policy": "no-referrer-when-downgrade"}
        )
        header_config = nginx._get_http_headers()
        self.assertIn(
            ("Referrer-Policy", "no-referrer-when-downgrade"),
            header_config,
        )

    def test_invalid_header_referrerPolicy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"Referrer-Policy": "no-referrr-when-downgrade"}
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_header_accessControl(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"Access-Control-Allow-Origin": "*"}
        )
        header_config = nginx._get_http_headers()
        self.assertIn(("Access-Control-Allow-Origin", "*"), header_config)

    def test_invalid_header_accessControl(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"Access-Control-Allow-Origin": "htps://this.is.mydomain.nl"}
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_header_contentType(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Content-Type-Options": "nosniff"}
        )
        header_config = nginx._get_http_headers()
        self.assertIn(("X-Content-Type-Options", "nosniff"), header_config)

    def test_invalid_header_contentType(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps({"X-Content-Type-Options": ""})
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_header_contentSecurity(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Content-Security-Policy": "default-src https: \u0027unsafe-eval\u0027 \u0027unsafe-inline\u0027; object-src \u0027none\u0027"  # noqa: C0301
            }
        )
        header_config = nginx._get_http_headers()
        self.assertIn(
            (
                "Content-Security-Policy",
                "default-src https: \\'unsafe-eval\\' \\'unsafe-inline\\'; object-src \\'none\\'",  # noqa: C0301
            ),  # noqa: C0301
            header_config,
        )

    def test_valid_header_contentSecurity_sha(self):
        base64_src = r"default-src 'self'; style-src 'self' 'sha256-aBc/dEf='; script-src 'self' 'unsafe-eval' 'sha256-aBc+dEf=';"  # noqa: C0301

        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"Content-Security-Policy": base64_src}
        )
        header_config = nginx._get_http_headers()
        self.assertIn(
            (
                "Content-Security-Policy",
                base64_src.replace("'", "\\'"),
            ),
            header_config,
        )

    def test_invalid_header_contentSecurity(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Content-Security-Policy": "$# default-src https://my.csp.domain.amsterdam"  # noqa: C0301
            }
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_header_permittedPolicies(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Permitted-Cross-Domain-Policies": "by-content-type"}
        )
        header_config = nginx._get_http_headers()
        self.assertIn(
            ("X-Permitted-Cross-Domain-Policies", "by-content-type"),
            header_config,
        )

    def test_invalid_header_permittedPolicies(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-Permitted-Cross-Domain-Policies": "#%#^#^"}
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_header_xssProtection(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-XSS-Protection": "1; report=https://domainwithnewstyle.tld.consultancy"}
        )
        header_config = nginx._get_http_headers()
        self.assertIn(
            (
                "X-XSS-Protection",
                "1; report=https://domainwithnewstyle.tld.consultancy",
            ),
            header_config,
        )

    def test_invalid_header_xssProtection(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {"X-XSS-Protection": "1;mode=bock"}
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_header_partial(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Referrer-Policy": "no-referrr-when-downgrade",
                "Access-Control-Allow-Origin": "https://this.is.mydomain.nl",
                "X-Content-Type-Options": "nosniff",
            }
        )
        header_config = nginx._get_http_headers()
        self.assertNotIn(
            (
                "X-XSS-Protection",
                "1; report=https://domainwithnewstyle.tld.consultancy",
            ),
            header_config,
        )

    def test_invalid_header_json(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = "invalid"
        with self.assertRaises(ValueError):
            nginx._get_http_headers()

    def test_valid_header_originTrial(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Origin-Trial": "ArmVE2nkyn2sDf+DNN9MJVBYCagx:+NCFIc7=="
            }
        )
        header_config = nginx._get_http_headers()
        self.assertIn(
            ("Origin-Trial",
             "ArmVE2nkyn2sDf+DNN9MJVBYCagx:+NCFIc7==",
            ),
            header_config,
        )
    def test_inValid_header_originTrial(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Origin-Trial": "#####"
            }
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_header_cross_origin_resource_policy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Cross-Origin-Resource-Policy": "same-origin"
            }
        )
        header_config = nginx._get_http_headers()
        self.assertIn(
            ("Cross-Origin-Resource-Policy",
             "same-origin",
             ),
            header_config,
        )
    def test_invalid_header_cross_origin_resource_policy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Cross-Origin-Resource-Policy": "#####"
            }
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_header_cross_origin_opener_policy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Cross-Origin-Opener-Policy": "same-origin"
            }
        )
        header_config = nginx._get_http_headers()
        self.assertIn(
            ("Cross-Origin-Opener-Policy",
             "same-origin",
             ),
            header_config,
        )
    def test_invalid_header_cross_origin_opener_policy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Cross-Origin-Opener-Policy": "&^%$#"
            }
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_header_cross_origin_embedder_policy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Cross-Origin-Embedder-Policy": "require-corp"
            }
        )
        header_config = nginx._get_http_headers()
        self.assertIn(
            ("Cross-Origin-Embedder-Policy",
             "require-corp",
             ),
            header_config,
        )
    def test_invalid_header_cross_origin_embedder_policy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Cross-Origin-Embedder-Policy": "&^as%$#"
            }
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)

    def test_valid_header_clear_site_data_policy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Clear-Site-Data": "executionContexts"
            }
        )
        header_config = nginx._get_http_headers()
        self.assertIn(
            ("Clear-Site-Data",
             "executionContexts",
             ),
            header_config,
        )
    def test_invalid_header_clear_site_data_policy(self):
        os.environ["HTTP_RESPONSE_HEADERS"] = json.dumps(
            {
                "Clear-Site-Data": "&^as%$#"
            }
        )
        header_config = nginx._get_http_headers()
        self.assertEqual([], header_config)
