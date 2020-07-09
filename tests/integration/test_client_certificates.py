import base64
import json
from socket import gethostname

from OpenSSL import crypto

from tests.integration import basetest


class TestCaseClientCertificates(basetest.BaseTest):

    certificate = None

    def setUp(self):
        super().setUp()
        self.certificate = self._create_self_signed_cert()

    def _create_self_signed_cert(self):

        # Create a key pair
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, 1024)

        # Create a self-signed cert
        cert = crypto.X509()
        cert.get_subject().C = "NL"
        cert.get_subject().ST = "Rotterdam"
        cert.get_subject().L = "Rotterdam"
        cert.get_subject().O = "Mendix"  # noqa: E741
        cert.get_subject().OU = "Mendix"
        cert.get_subject().CN = gethostname()
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(k)
        cert.sign(k, "sha1")

        # Create a P12 container
        p12 = crypto.PKCS12()
        p12.set_certificate(cert)

        return p12.export()

    # The following two tests ensure that the certificates are being loaded into the right configuration key
    # Mendix 7.20 deprecated WebServiceClientCertificates in favour of ClientCertificateUsagess
    def test_selfsigned_certificate_less_mx720(self):
        self._test_selfsigned_certificate("BuildpackTestApp-mx-7-16.mda")
        self.assert_string_in_recent_logs("WebServiceClientCertificates")

    def test_selfsigned_certificate_greq_mx720(self):
        self._test_selfsigned_certificate("Mendix8.1.1.58432_StarterApp.mda")
        self.assert_string_not_in_recent_logs("WebServiceClientCertificates")

    def _test_selfsigned_certificate(self, mda):
        certificates = [
            {
                "pfx": base64.b64encode(self.certificate).decode("utf-8"),
                "password": "",
                "pin_to": [],
            }
        ]

        self.stage_container(
            mda, env_vars={"CLIENT_CERTIFICATES": json.dumps(certificates)}
        )
        self.start_container()
        self.assert_app_running()
