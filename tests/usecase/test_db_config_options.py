import os
import unittest
from database_config import get_database_config


class TestDatabaseConfigOptions(unittest.TestCase):
    def clean_env(self):
        """
        Setting different environment variables for test in the same process
        can lead to flaky tests.
        """
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
            get_database_config()

    def test_mx_runtime_db_config(self):
        """
        Test is MXRUNTIME variables are set up no database configuration is returned
        based on DATABASE_URL or VCAP_SERVICES
        """
        self.clean_env()
        os.environ["MXRUNTIME_DatabaseType"] = "PostgreSQL"
        os.environ[
            "MXRUNTIME_DatabaseJdbcUrl"
        ] = "postgres://username:password@rdsbroker-testfree-nonprod-1-eu-west-1.asdbjasdg.eu-west-1.rds.amazonaws.com:5432/testdatabase"  # noqa E501

        config = get_database_config()
        assert not config

    def test_database_url(self):
        self.clean_env()
        os.environ[
            "DATABASE_URL"
        ] = "jdbc:postgres://user:secret@host/database"

        config = get_database_config()
        assert config
        assert config["DatabaseType"] == "PostgreSQL"

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

        config = get_database_config()
        assert config
        assert config["DatabaseType"] == "PostgreSQL"
