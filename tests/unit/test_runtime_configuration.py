import base64
import json
import os
from socket import gethostname
from unittest import TestCase, mock

from buildpack import util
from buildpack.core import runtime, security
from lib.m2ee.version import MXVersion
from OpenSSL import crypto


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
        assert (
            "runtime_max_threads" in result
            and "max_form_content_size" in result
        )

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
            "CUSTOM_RUNTIME_SETTINGS": json.dumps(
                {"SourceDatabaseType": "MySQL"}
            ),
        },
    )
    def test_custom_runtime_setting_is_set(self):
        result = runtime._get_custom_runtime_settings()
        assert (
            "PersistentSessions" in result
            and result["SourceDatabaseType"] == "MySQL"
        )


def _create_self_signed_cert():
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


class TestClientCertificateConfiguration(TestCase):

    CERTIFICATE_ENV = {
        "CLIENT_CERTIFICATES": json.dumps(
            [
                {
                    "pfx": base64.b64encode(_create_self_signed_cert()).decode(
                        "utf-8"
                    ),
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
