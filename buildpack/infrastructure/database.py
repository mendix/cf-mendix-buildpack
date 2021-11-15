import json
import logging
import os
import re
import shutil
import tempfile
from abc import ABC, abstractmethod
from cryptography.hazmat.primitives import serialization
from urllib.parse import parse_qs, unquote, urlencode

from buildpack import util


def get_config():
    # the following options are validated to get database credentials
    # 1) existence of custom runtime settings Database.... values
    # 2) VCAP with database credentials
    # 3) existence of DATABASE_URL env var

    # In case we find MXRUNTIME_Database.... values we don't interfere and
    # return nothing. VCAP or DATABASE_URL return m2ee configuration

    if any(
        [x.startswith("MXRUNTIME_Database") for x in list(os.environ.keys())]
    ):
        logging.debug(
            "Detected database configuration using custom runtime settings."
        )
        return None

    factory = DatabaseConfigurationFactory()
    configuration = factory.get_instance()

    if configuration:
        m2ee_config = configuration.get_m2ee_configuration()
        if m2ee_config and "DatabaseType" in m2ee_config:
            return m2ee_config

    raise RuntimeError(
        "Can't find database configuration from environment variables. "
        "Check README for supported configuration options."
    )


class DatabaseConfigurationFactory:
    # Returns a DatabaseConfiguration instance to return database configuration
    # for the Mendix runtime

    def __init__(self):
        self.vcap_services = util.get_vcap_services_data()

    def get_instance(self):
        # explicit detect supported configurations
        if self.present_in_vcap(
            "hana", tags=["hana", "database", "relational"]
        ):
            return SapHanaDatabaseConfiguration(
                self.vcap_services["hana"][0]["credentials"]
            )

        if self.present_in_vcap(
            "hanatrial", tags=["hana", "database", "relational"]
        ):
            return SapHanaDatabaseConfiguration(
                self.vcap_services["hanatrial"][0]["credentials"]
            )

        # fallback to original configuration
        url = self.get_database_uri_from_vcap(self.vcap_services)
        if not url and "DATABASE_URL" in os.environ:
            url = os.environ["DATABASE_URL"]

        if url:
            return UrlDatabaseConfiguration(url)

        return None

    def present_in_vcap(self, service_name, tags=None):
        tag_set = set()
        if tags:
            tag_set = set(tags)

        # Check if service is available in vcap and given tags match
        if service_name is not None:
            present = service_name in self.vcap_services
            if not present:
                return False

            binding = self.vcap_services[service_name][0]
            result = set(binding["tags"])

            return result & tag_set == tag_set

        # Loop services when no service name given, check types
        for binding in [
            self.vcap_services[service][0] for service in self.vcap_services
        ]:
            if set(binding["tags"]) & tag_set == tag_set:
                return True

        return False

    def get_database_uri_from_vcap(self, vcap_services):
        for service_type_name in (
            "p-mysql",
            "p.mysql",
            "elephantsql",
            "cleardb",
            "PostgreSQL",
            "dashDB",
            "mariadb",
            "postgresql",
            "rds",
            "postgresql_shared",
        ):
            if vcap_services and service_type_name in vcap_services:
                return vcap_services[service_type_name][0]["credentials"][
                    "uri"
                ]

        if "azure-sqldb" in vcap_services:
            return vcap_services["azure-sqldb"][0]["credentials"]["jdbcUrl"]

        for key in vcap_services:
            try:
                uri = vcap_services[key][0]["credentials"]["uri"]
                if (
                    key.startswith("rds")
                    or key.startswith("dashDB")
                    or uri.startswith("postgres")
                    or uri.startswith("mysql")
                ):
                    return uri
            except (TypeError, KeyError):
                pass

        return None


class DatabaseConfiguration(ABC):
    # Base class for database configurations. Implements only the basics.

    def __init__(self, env_vars=None):
        # env_vars may be copy of the environment variables,
        # os.environ, for unit testing
        if env_vars:
            self.env_vars = env_vars
        else:
            self.env_vars = os.environ

        self.development_mode = (
            self.env_vars.get("DEVELOPMENT_MODE", "").lower() == "true"
        )

    def get_m2ee_configuration(self):
        # Return the m2ee configuration for connection to the database

        self.init()

        m2ee_config = {
            "DatabaseType": self.get_database_type(),
            "DatabaseHost": self.get_database_host(),
            "DatabaseUserName": unquote(self.get_database_username()),
            "DatabasePassword": unquote(self.get_database_password()),
            "DatabaseName": self.get_database_name(),
            "DatabaseJdbcUrl": self.get_database_jdbc_url(),
        }

        m2ee_config.update(self.get_additional_m2ee_config())

        if self.development_mode:
            m2ee_config.update(
                {
                    "ConnectionPoolingMaxIdle": 1,
                    "ConnectionPoolingMaxActive": 20,
                    "ConnectionPoolingNumTestsPerEvictionRun": 50,
                    "ConnectionPoolingSoftMinEvictableIdleTimeMillis": 1000,
                    "ConnectionPoolingTimeBetweenEvictionRunsMillis": 1000,
                }
            )

        # Strip empty values
        filter_m2ee_config = {k: v for k, v in m2ee_config.items() if v}
        logging.debug(
            "Returning database configuration: %s",
            json.dumps(filter_m2ee_config),
        )

        return filter_m2ee_config

    def get_override_connection_params(self):
        params_str = self.env_vars.get("DATABASE_CONNECTION_PARAMS", "{}")
        try:
            params = json.loads(params_str)
            return params
        except Exception:
            logging.warning(
                "Invalid JSON string for DATABASE_CONNECTION_PARAMS."
                "Ignoring value."
            )
            return {}

    @abstractmethod
    def init(self):
        # Parse the configuration. This method should read the source (either
        # vcap or environment variables) to make it possible that methods are
        # get_dabatabase_hostname can work
        pass

    @abstractmethod
    def get_database_type(self):
        # Return the database type for the M2EE configuration
        pass

    @abstractmethod
    def get_database_host(self):
        # Return the database host for the M2EE configuration
        pass

    @abstractmethod
    def get_database_username(self):
        # Return the username for the M2EE configuration
        pass

    @abstractmethod
    def get_database_password(self):
        # Return the password for the M2EE configuration
        pass

    @abstractmethod
    def get_database_jdbc_url(self):
        # Return the database jdbc url for the M2EE configuration

        # Implementations should use get_override_connection_parameters
        # allowing users to adjust or extend the parameters retrieved
        # from the VCAP.
        pass

    @abstractmethod
    def get_database_name(self):
        # Return the database name for the M2EE configuration
        pass

    @abstractmethod
    def get_additional_m2ee_config(self):
        return {}


class UrlDatabaseConfiguration(DatabaseConfiguration):
    # Returns a database configuration based on the original code from util.

    SSLROOTCERT = "sslrootcert"

    SSLKEY = "sslkey"

    SSLCERT = "sslcert"

    def __init__(self, url, env_vars=None):
        super().__init__(env_vars)
        logging.debug("Detected URL based database configuration.")
        self.url = url
        self.m2ee_config = None

    def init(self):
        patterns = [
            r"(?P<type>[a-zA-Z0-9]+)://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^/]+)/(?P<dbname>[^?]*)(?P<extra>\?.*)?",  # noqa: E501
            r"jdbc:(?P<type>[a-zA-Z0-9]+)://(?P<host>[^;]+);database=(?P<dbname>[^;]*);user=(?P<user>[^;]+);password=(?P<password>.*)$",  # noqa: E501
        ]

        supported_databases = {
            "postgres": "PostgreSQL",
            "postgresql": "PostgreSQL",
            "mysql": "MySQL",
            "db2": "Db2",
            "sqlserver": "SQLSERVER",
        }

        for pattern in patterns:
            match = re.search(pattern, self.url)
            if match is not None:
                break
        else:
            raise Exception(
                "Could not parse database credentials from database URI"
            )

        database_type_input = match.group("type")
        if database_type_input not in supported_databases:
            raise Exception(
                "Unknown database type: {}".format(database_type_input)
            )
        database_type = supported_databases[database_type_input]

        config = {
            "DatabaseType": database_type,
            "DatabaseUserName": match.group("user"),
            "DatabasePassword": match.group("password"),
            "DatabaseHost": match.group("host"),
            "DatabaseName": match.group("dbname"),
        }

        # parsing additional parameters
        # 1) check for sslmode in existing jdbc url for m2ee config
        # 2) update jdbc url (from vcap) with input
        # from DATABASE_CONNECTION_PARAMS
        jdbc_params = {}

        # getting values from url
        has_extra = "extra" in match.groupdict() and match.group("extra")
        if has_extra:
            extra = match.group("extra").lstrip("?")
            jdbc_params = parse_qs(extra)

        # defaults
        if database_type == "PostgreSQL":
            jdbc_params.update({"tcpKeepAlive": "true"})

        if database_type == "PostgreSQL" and config["DatabaseHost"].split(":")[
            0
        ].endswith(".rds.amazonaws.com"):
            jdbc_params.update(
                {
                    "sslrootcert": os.path.expandvars(
                        "$HOME/.postgresql/amazon-rds-ca.pem"
                    )
                }
            )
            jdbc_params.update({"sslmode": "verify-full"})

        if database_type == "PostgreSQL" and not self.url.startswith("jdbc:"):
            self.extract_inline_cert(
                jdbc_params, self.SSLCERT, "postgresql.crt"
            )
            self.extract_inline_cert(
                jdbc_params, self.SSLKEY, "postgresql.pk8"
            )
            self.extract_inline_cert(jdbc_params, self.SSLROOTCERT, "root.crt")

        extra_url_params_str = self.env_vars.get(
            "DATABASE_CONNECTION_PARAMS", "{}"
        )
        if extra_url_params_str is not None:
            try:
                extra_url_params = json.loads(extra_url_params_str)
                jdbc_params.update(extra_url_params)
            except Exception:
                logging.warning(
                    "Invalid JSON string for DATABASE_CONNECTION_PARAMS"
                )

        # generate jdbc_url, might be None
        jdbc_url = self.get_jdbc_strings(self.url, config, jdbc_params)
        if jdbc_url is not None:
            logging.debug("Setting JDBC url: %s", jdbc_url)
            config.update({"DatabaseJdbcUrl": jdbc_url})

        if "sslmode" in jdbc_params:
            sslmode = jdbc_params["sslmode"]
            if sslmode and sslmode[0] == "require":
                config.update({"DatabaseUseSsl": True})

        self.m2ee_config = config

    def extract_inline_cert(self, jdbc_params, param, filename):
        lst = jdbc_params.get(param)
        if lst is not None:
            if not isinstance(lst, list):
                lst = [lst]
                jdbc_params[param] = lst
            for i, inline in enumerate(lst):
                if inline.startswith("-----BEGIN"):
                    tmp_cert_file = self.create_cert_file(filename)
                    try:
                        logging.debug(
                            "extract %s to %s", param, tmp_cert_file.name
                        )
                        if inline.startswith(
                            "-----BEGIN RSA PRIVATE KEY-----"
                        ):
                            self.to_pk8(inline, tmp_cert_file)
                        else:
                            tmp_cert_file.write(inline.encode())
                    finally:
                        tmp_cert_file.close()
                    lst[i] = self.to_java_path(tmp_cert_file.name)

    @classmethod
    def to_java_path(cls, file_path):
        # Convert absolute path to the java subsystem
        return file_path

    @classmethod
    def to_pk8(cls, inline, tmp_cert_file):
        private_key = serialization.load_pem_private_key(
            inline.encode(), password=None
        )
        keybytes = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        tmp_cert_file.write(keybytes)

    @classmethod
    def create_cert_file(cls, default_file_name):
        (prefix, suffix) = os.path.splitext(default_file_name)
        return tempfile.NamedTemporaryFile(
            mode="wb", suffix=suffix, prefix=prefix, delete=False
        )

    def get_jdbc_strings(self, url, config, jdbc_params):
        # JDBC strings might be different from connection uri strings
        # retrieved from the VCAP
        # For supported/tested situations we'll create a JDBC string based on
        # * url (from VCAP or DATABASE_URL)
        # * config (extracted information from url)
        # * jdbc_params (from DATABASE_URL or DATABASE_CONNECTION_PARAMS)
        #
        # if given url is a JDBC string this will be returned
        #

        # return unmodified jdbc string
        if url.startswith("jdbc:"):
            return url

        if len(jdbc_params) > 0:
            extra_jdbc_params = "?{}".format(urlencode(jdbc_params, True))
        else:
            extra_jdbc_params = ""

        if config["DatabaseType"] == "PostgreSQL":
            jdbc_url = "jdbc:postgresql://{}/{}{}".format(
                config["DatabaseHost"],
                config["DatabaseName"],
                extra_jdbc_params,
            )
            return jdbc_url

    def get_database_type(self):
        return self.m2ee_config.get("DatabaseType")

    def get_database_host(self):
        return self.m2ee_config.get("DatabaseHost")

    def get_database_username(self):
        return self.m2ee_config.get("DatabaseUserName")

    def get_database_password(self):
        return self.m2ee_config.get("DatabasePassword")

    def get_database_jdbc_url(self):
        return self.m2ee_config.get("DatabaseJdbcUrl")

    def get_database_name(self):
        """Return the database name for the M2EE configuration"""
        return self.m2ee_config.get("DatabaseName")

    def get_additional_m2ee_config(self):
        if self.m2ee_config["DatabaseType"] == "MySQL":
            return {
                "ConnectionPoolingNumTestsPerEvictionRun": 50,
                "ConnectionPoolingSoftMinEvictableIdleTimeMillis": 10000,
                "ConnectionPoolingTimeBetweenEvictionRunsMillis": 10000,
            }

        return {}


class SapHanaDatabaseConfiguration(DatabaseConfiguration):

    database_type = "SAPHANA"

    def __init__(self, credentials, env_vars=None):
        super().__init__(env_vars)
        logging.debug("Detected SAP Hana configuration.")
        self.credentials = credentials

    def init(self):
        pass

    def get_database_type(self):
        return self.database_type

    def get_database_host(self):
        return "{}:{}".format(
            self.credentials.get("host"), self.credentials.get("port")
        )

    def get_database_username(self):
        return self.credentials.get("user")

    def get_database_password(self):
        return self.credentials.get("password")

    def get_database_jdbc_url(self):
        """Return the database jdbc url for the M2EE configuration"""
        url = self.credentials.get("url", "")
        pattern = r"jdbc:sap://(?P<host>[^:]+):(?P<port>[0-9]+)/?(?P<q>\?(?P<params>.*))?$"  # noqa:E501
        match = re.search(pattern, url)
        if match is None:
            logging.error(
                "Unable to parse Hana JDBC url string for parameters"
            )
            raise Exception(
                "Unable to parse Hana JDBC url string for parameters"
            )

        parameters = {}
        if match.group("q") is not None and match.group("params") is not None:
            q = match.group("q")
            params = match.group("params")
            parameters.update(parse_qs(params))

        # override parameters from DATABASE_CONNECTION_PARAMS
        parameters.update(self.get_override_connection_params())

        if q is not None and len(parameters) > 0:
            parameter_str = "?{}".format(urlencode(parameters, True))
            url = url.replace(q, parameter_str)

        return url

    def get_database_name(self):
        return self.credentials.get("schema")

    def get_additional_m2ee_config(self):
        return {}


def stage(buildpack_dir, build_dir):
    logging.debug("Staging database...")
    util.mkdir_p(os.path.join(build_dir, ".postgresql"))
    shutil.copy(
        os.path.join(buildpack_dir, "etc", "amazon-rds-ca.pem"),
        os.path.join(build_dir, ".postgresql", "amazon-rds-ca.pem"),
    )


def update_config(m2ee):
    # db configuration might be None, database should then be set up with
    # MXRUNTIME_Database... custom runtime settings.
    runtime_db_config = get_config()
    if runtime_db_config:
        util.upsert_custom_runtime_settings(
            m2ee, runtime_db_config, overwrite=True, append=True
        )
