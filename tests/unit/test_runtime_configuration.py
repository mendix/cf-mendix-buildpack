import base64
import json
import os
from datetime import datetime, timedelta
from socket import gethostname
from unittest import TestCase, mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from buildpack import util
from buildpack.core import runtime, security
from lib.m2ee.version import MXVersion


class M2EEMock:
    class ConfigMock:
        def __init__(self):
            self._conf = {}

    def __init__(self):
        self.config = self.ConfigMock()


class TestJettyConfiguration(TestCase):
    def _set_and_get_jetty_settings(self):
        m2ee = M2EEMock()
        m2ee.config._conf = {util.M2EE_TOOLS_SETTINGS_SECTION: {}}
        # The default m2ee-tools configuration contains max_form_content_size: 10485760
        util.upsert_m2ee_tools_setting(
            m2ee,
            "jetty",
            {"max_form_content_size": 10485760},
            overwrite=True,
            append=True,
        )
        runtime._set_jetty_config(m2ee)
        return util.get_m2ee_tools_setting(m2ee, "jetty")

    @mock.patch.dict(
        os.environ, {"JETTY_CONFIG": json.dumps({"runtime_max_threads": 500})}
    )
    def test_upsert_valid_jetty_settings(self):
        result = self._set_and_get_jetty_settings()
        assert "runtime_max_threads" in result and "max_form_content_size" in result

    @mock.patch.dict(os.environ, {"JETTY_CONFIG": "invalid_json"})
    def test_upsert_invalid_jetty_settings(self):
        result = self._set_and_get_jetty_settings()
        assert len(result) == 1


class TestConstantConfiguration(TestCase):
    @mock.patch.dict(
        os.environ,
        {
            "MX_AppCloudServices_OpenIdProvider": "http://localhost",
            "CONSTANTS": json.dumps(
                {
                    "AppCloudServices.OpenIdEnabled": True,
                    "AppCloudServices.OpenIdProvider": "http://google.com/",
                }
            ),
        },
    )
    def test_constant_is_set(self):
        metadata = {
            "Constants": [
                {"Name": "AppCloudServices.OpenIdEnabled", "Type": "string"},
                {"Name": "AppCloudServices.OpenIdProvider", "Type": "string"},
            ]
        }
        result = runtime._get_constants(metadata)

        assert result["AppCloudServices.OpenIdProvider"] == "http://localhost"


class TestCustomRuntimeConfiguration(TestCase):
    @mock.patch.dict(
        os.environ,
        {
            "MXRUNTIME_PersistentSessions": "True",
            "CUSTOM_RUNTIME_SETTINGS": json.dumps({"SourceDatabaseType": "MySQL"}),
        },
    )
    def test_custom_runtime_setting_is_set(self):
        result = runtime._get_custom_runtime_settings()
        assert (
            "PersistentSessions" in result and result["SourceDatabaseType"] == "MySQL"
        )


class TestClientCertificateConfiguration(TestCase):
    def _create_self_signed_cert():  # pylint: disable=no-method-argument
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

        # Serialize private key and certificate to a PKCS12 container
        p12 = pkcs12.serialize_key_and_certificates(
            name=b"selfsigned",
            key=private_key,
            cert=cert,
            cas=None,
            encryption_algorithm=serialization.NoEncryption()
        )

        return p12

    CERTIFICATE_ENV = {
        "CLIENT_CERTIFICATES": json.dumps(
            [
                {
                    "pfx": base64.b64encode(_create_self_signed_cert()).decode("utf-8"),
                    "password": "",
                    "pin_to": [],
                }
            ]
        )
    }

    @mock.patch.dict(os.environ, CERTIFICATE_ENV)
    def test_selfsigned_certificate_less_mx720(self):
        result = security.get_client_certificates(MXVersion(7.16))
        assert "WebServiceClientCertificates" in result

    @mock.patch.dict(os.environ, CERTIFICATE_ENV)
    def test_selfsigned_certificate_greq_mx720(self):
        result = security.get_client_certificates(MXVersion(7.23))
        assert "ClientCertificateUsages" in result
