import base64
from datetime import datetime, timedelta
from socket import gethostname

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from tests.integration import basetest


class TestCaseCertificateAuthorities(basetest.BaseTest):

    certificate = None

    def setUp(self):
        super().setUp()
        self.certificate = self._create_self_signed_cert()

    def _create_self_signed_cert(self):
        # Generate a private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Create a self-signed certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "NL"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Rotterdam"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Rotterdam"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Mendix"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Mendix"),
            x509.NameAttribute(NameOID.COMMON_NAME, gethostname()),
        ])
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            1000
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365*10)
        ).add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True,
        ).sign(private_key, hashes.SHA256())

        cert_pem = cert.public_bytes(serialization.Encoding.PEM)

        return cert_pem

    def test_certificate_authorities(self):
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"CERTIFICATE_AUTHORITIES": self.certificate},
        )
        self.start_container()
        self.assert_app_running()
        self.assert_string_in_recent_logs("Core: Added 1 authority certificate(s)")

    def test_certificate_authorities_base64(self):
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"CERTIFICATE_AUTHORITIES": base64.b64encode(self.certificate)},
        )
        self.start_container()
        self.assert_app_running()
        self.assert_string_in_recent_logs("Core: Added 1 authority certificate(s)")
