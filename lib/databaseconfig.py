import json
import logging
import os
import re
import buildpackutil
from urllib.parse import parse_qs, urlencode
from m2ee import logger  # noqa: E402


class DatabaseConfigurationFactory:
    """Returns a DatabaseConfiguration instance to return database configuration
    for the Mendix runtime"""

    def get_instance(self):
        # explicit detect supported configurations
        vcap_services = buildpackutil.get_vcap_services_data()

        if "hana" in vcap_services:
            return SapHanaDatabaseConfiguration(vcap_services["hana"][0]["credentials"])

        # fallback to original configuration
        url = self.get_database_uri_from_vcap(vcap_services)
        if url is None:
            url = os.environ["DATABASE_URL"]

        if url is not None:
            return UrlDatabaseConfiguration(url)

        return None

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
                if key.startswith("rds"):
                    return uri
                if key.startswith("dashDB"):
                    return uri
                if uri.startswith("postgres"):
                    return uri
                if uri.startswith("mysql"):
                    return uri
            except (TypeError, KeyError):
                pass

        return None


class DatabaseConfiguration:
    """Base clase for database configurations. Implements only the basics."""

    development_mode = os.getenv("DEVELOPMENT_MODE", "").lower() == "true"

    def __init__(self):
        pass

    def get_database_configuration(self):
        """Return the m2ee configuration for connection to the database"""
        config = self.parse_configuration()

        if self.development_mode:
            config.update(
                {
                    "ConnectionPoolingMaxIdle": 1,
                    "ConnectionPoolingMaxActive": 20,
                    "ConnectionPoolingNumTestsPerEvictionRun": 50,
                    "ConnectionPoolingSoftMinEvictableIdleTimeMillis": 1000,
                    "ConnectionPoolingTimeBetweenEvictionRunsMillis": 1000,
                }
            )

        logging.debug("Returning database configuration: {}".format(json.dumps(config)))

        return config

    def parse_configuration(self):
        """Parse the configuration, this should be handled by implementations"""
        return {}


class UrlDatabaseConfiguration(DatabaseConfiguration):
    """Returns a database configuration compatible with the original code from buildpackutil"""

    def __init__(self, url):
        logger.info("Detected URL based database configuration.")
        self.url = url

    def parse_configuration(self):
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
                "Could not parse database credentials from database uri %s"
                % self.url
            )

        database_type_input = match.group("type")
        if database_type_input not in supported_databases:
            raise Exception("Unknown database type: %s", database_type_input)
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
        # 2) update jdbc url (from vcap) with input from DATABASE_CONNECTION_PARAMS
        jdbc_params = {}

        # getting values from url
        has_extra = "extra" in match.groupdict() and match.group("extra")
        if has_extra:
            extra = match.group("extra").lstrip("?")
            jdbc_params = parse_qs(extra)

        # defaults
        if database_type == "PostgreSQL":
            jdbc_params.update({"tcpKeepAlive": "true"})

        extra_url_params_str = os.getenv("DATABASE_CONNECTION_PARAMS", "{}")
        if extra_url_params_str is not None:
            try:
                extra_url_params = json.loads(extra_url_params_str)
                jdbc_params.update(extra_url_params)
            except Exception:
                logger.warning(
                    "Invalid JSON string for DATABASE_CONNECTION_PARAMS"
                )

        # generate jdbc_url, might be None
        jdbc_url = self.get_jdbc_strings(self.url, match, config, jdbc_params)
        if jdbc_url is not None:
            logger.debug("Setting JDBC url: {}".format(jdbc_url))
            config.update({"DatabaseJdbcUrl": jdbc_url})

        if "sslmode" in jdbc_params:
            sslmode = jdbc_params["sslmode"]
            if sslmode and sslmode[0] == "require":
                config.update({"DatabaseUseSsl": True})

        if database_type_input == "mysql":
            config.update(
                {
                    "ConnectionPoolingNumTestsPerEvictionRun": 50,
                    "ConnectionPoolingSoftMinEvictableIdleTimeMillis": 10000,
                    "ConnectionPoolingTimeBetweenEvictionRunsMillis": 10000,
                }
            )

        return config

    def get_jdbc_strings(self, url, match, config, jdbc_params):
        # JDBC strings might be different from connection uri strings retrieved from the VCAP
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
            extra_jdbc_params = "?{}".format(urlencode(jdbc_params))
        else:
            extra_jdbc_params = ""

        if config["DatabaseType"] == "PostgreSQL":
            jdbc_url = "jdbc:postgresql://{}/{}{}".format(
                config["DatabaseHost"],
                config["DatabaseName"],
                extra_jdbc_params,
            )
            return jdbc_url


class SapHanaDatabaseConfiguration(DatabaseConfiguration):

    datababase_type = "SAPHANA"

    def __init__(self, credentials):
        logger.info("Detected SAP Hana configuration.")
        self.credentials = credentials

    def parse_configuration(self):
        url = self.credentials["url"]
        schema = self.credentials["schema"]
        host = "{}:{}".format(
            self.credentials["host"], self.credentials["port"]
        )
        username = self.credentials["user"]
        password = self.credentials["password"]

        return {
            "DatabaseType": self.datababase_type,
            "DatabaseJdbcUrl": url,
            "DatabaseHost": host,
            "DatabaseUserName": username,
            "DatabasePassword": password,
            "DatabaseName": schema,
        }
