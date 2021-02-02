import base64
import json
from socket import gethostname

from OpenSSL import crypto

from tests.integration import basetest


class TestCaseCertificateAuthorities(basetest.BaseTest):

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

        # Return a .PEM certificate
        return crypto.dump_certificate(crypto.FILETYPE_PEM, cert)

    def test_certificate_authorities(self):
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"CERTIFICATE_AUTHORITIES": self.certificate},
        )
        self.start_container()
        self.assert_app_running()
        self.assert_string_in_recent_logs(
            "Core: Added 1 authority certificate(s)"
        )

    def test_certificate_authorities_base64(self):
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={
                "CERTIFICATE_AUTHORITIES": base64.b64encode(self.certificate)
            },
        )
        self.start_container()
        self.assert_app_running()
        self.assert_string_in_recent_logs(
            "Core: Added 1 authority certificate(s)"
        )
