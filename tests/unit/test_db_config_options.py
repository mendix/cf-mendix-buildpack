import datetime
import os
import unittest

from urllib.parse import parse_qs, urlparse, urlencode, urlunparse
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509 import NameAttribute
from cryptography.x509.base import Certificate
from cryptography.x509.oid import NameOID
from buildpack.infrastructure.database import (
    get_config,
    UrlDatabaseConfiguration,
)


class TestDatabaseConfigOptions(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cert_map = {}

    def clean_env(self):

        # Setting different environment variables for test in the same process
        # can lead to flaky tests.

        if "DATABASE_URL" in os.environ.keys():
            del os.environ["DATABASE_URL"]

        for key in filter(
            lambda x: x.startswith("MXRUNTIME_Database"),
            list(os.environ.keys()),
        ):
            del os.environ[key]

    def test_no_setup(self):
        self.clean_env()
        with self.assertRaises(RuntimeError):
            get_config()

    def test_mx_runtime_db_config(self):

        # Test if MXRUNTIME variables are set up if no database configuration is returned
        # based on DATABASE_URL or VCAP_SERVICES

        self.clean_env()
        os.environ["MXRUNTIME_DatabaseType"] = "PostgreSQL"
        os.environ[
            "MXRUNTIME_DatabaseJdbcUrl"
        ] = "jdbc:postgresql://username:password@rdsbroker-testfree-nonprod-1-eu-west-1.asdbjasdg.eu-west-1.rds.amazonaws.com:5432/testdatabase"  # noqa E501

        config = get_config()
        assert not config

    def test_database_url(self):
        self.clean_env()
        os.environ[
            "DATABASE_URL"
        ] = "jdbc:postgres://user:secret@host/database"

        config = get_config()
        assert config
        assert config["DatabaseType"] == "PostgreSQL"

    def test_inline_certs(self):
        self.cert_map = CertGen().cert_map
        self.clean_env()
        c = UrlDatabaseConfiguration
        native_params = {
            c.SSLCERT: self.get_cert("postgresql.crt"),
            c.SSLROOTCERT: self.get_cert("root.crt"),
            c.SSLKEY: self.get_cert("postgresql.rsa.key"),
        }
        parts = urlparse("postgres://user:secret@host/database")
        parts = parts._replace(query=urlencode(native_params))
        native_url = urlunparse(parts)
        os.environ["DATABASE_URL"] = native_url

        config = get_config()
        assert config
        assert config["DatabaseType"] == "PostgreSQL"
        native_params[c.SSLKEY] = self.get_cert("postgresql.pk8")
        jdbc_params = parse_qs(urlparse(config["DatabaseJdbcUrl"]).query)
        self.cmp_cert(native_params, jdbc_params, c.SSLCERT)
        self.cmp_cert(native_params, jdbc_params, c.SSLROOTCERT)
        self.cmp_cert(native_params, jdbc_params, c.SSLKEY)

    def get_cert(self, cert_resource):
        return self.cert_map[cert_resource]

    @classmethod
    def cmp_cert(cls, native_params, jdbc_params, param):
        expected_string = native_params[param]
        actual_file = jdbc_params[param][0]
        with open(actual_file, "rb") as io_actual:
            actual_string = io_actual.read().decode("iso-8859-1")
            assert expected_string == actual_string, param + " differ"
        os.remove(actual_file)

    def test_vcap(self):
        self.clean_env()
        os.environ[
            "VCAP_SERVICES"
        ] = """
{
 "rds-testfree": [
   {
    "binding_name": null,
    "credentials": {
     "db_name": "dbuajsdhkasdhaks",
     "host": "rdsbroker-testfree-nonprod-1-eu-west-1.asdbjasdg.eu-west-1.rds.amazonaws.com",
     "password": "na8nanlayaona0--anbs",
     "uri": "postgres://ua98s7ananla:na8nanlayaona0--anbs@rdsbroker-testfree-nonprod-1-eu-west-1.asdbjasdg.eu-west-1.rds.amazonaws.com:5432/dbuajsdhkasdhaks",
     "username": "ua98s7ananla"
    },
    "instance_name": "ops-432a659e.test.foo.io-database",
    "label": "rds-testfree",
    "name": "ops-432a659e.test.foo.io-database",
    "plan": "shared-psql-testfree",
    "provider": null,
    "syslog_drain_url": null,
    "tags": [
     "database",
     "RDS",
     "postgresql"
    ],
    "volume_mounts": []
   }
  ]
}
    """  # noqa

        config = get_config()
        assert config
        assert config["DatabaseType"] == "PostgreSQL"


# Class to generate a test certificate chain
# https://cryptography.io/en/latest/x509/tutorial/
class CertGen:
    def __init__(self):
        self.init_root_cert()
        self.init_postgresql_cert()
        self.dump_to_storage()

    def dump_to_storage(self):
        self.cert_map = {}
        self._dump_cert(self.root_cert, "root.crt")
        self._dump_cert(self.postgresql_cert, "postgresql.crt")
        self._dump_key(
            self.postgresql_key,
            "postgresql.rsa.key",
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
        )
        self._dump_key(
            self.postgresql_key,
            "postgresql.pk8",
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
        )

    def _dump_key(self, key, keyout_name, enc, fmt):
        self.cert_map[keyout_name] = key.private_bytes(
            encoding=enc,
            format=fmt,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("iso-8859-1")

    def _dump_cert(self, cert: Certificate, out_name):
        self.cert_map[out_name] = cert.public_bytes(
            serialization.Encoding.PEM
        ).decode("iso-8859-1")

    def init_root_cert(self):
        self.root_key = self._newkey()
        ca_subj = x509.Name(
            [
                NameAttribute(NameOID.COUNTRY_NAME, u"US"),
                NameAttribute(NameOID.ORGANIZATION_NAME, u"Authority, Inc"),
                NameAttribute(NameOID.COMMON_NAME, u"Authority CA"),
            ]
        )
        self.root_cert = self._sign(
            ca_subj, self.root_key, ca_subj, self.root_key.public_key(), 3651
        )

    def init_postgresql_cert(self) -> Certificate:
        self.postgresql_key = self._newkey()
        subj = x509.Name(
            [
                NameAttribute(NameOID.COUNTRY_NAME, u"US"),
                NameAttribute(NameOID.ORGANIZATION_NAME, u"Authority, Inc"),
                NameAttribute(NameOID.COMMON_NAME, u"SQL Client"),
            ]
        )
        self.postgresql_cert = self._sign(
            self.root_cert.subject,
            self.root_key,
            subj,
            self.postgresql_key.public_key(),
            3650,
        )

    @classmethod
    def _newkey(cls):
        # Generate our key
        return rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

    @classmethod
    def _sign(
        cls, issuer: x509.Name, ca_key, subject: x509.Name, req_pub_key, days
    ) -> Certificate:
        # pylint: disable=too-many-arguments
        return (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(req_pub_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(
                # Our certificate will be valid for 10 days
                datetime.datetime.utcnow()
                + datetime.timedelta(days=days)
                # Sign our certificate with our private key
            )
            .sign(ca_key, hashes.SHA256())
        )
