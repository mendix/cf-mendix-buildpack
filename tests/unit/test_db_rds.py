import os

from buildpack.runtime_components.database import DatabaseConfigurationFactory

# IMPORTANT: to run this test successfully you need to set PYTHONPATH before
# running nosetest.
# export PYTHONPATH=<buildpack-root>/lib


class TestCaseRdsDryRun:

    rds_vcap_example = """
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

    urlencoded_rds_vcap_example = """
{
 "rds-testfree": [
   {
    "binding_name": null,
    "credentials": {
     "db_name": "dbuajsdhkasdhaks",
     "host": "rdsbroker-testfree-nonprod-1-eu-west-1.asdbjasdg.eu-west-1.rds.amazonaws.com",
     "password": "na8na%2Bnlay%26aona0--anbs",
     "uri": "postgres://ua98s7%3Fananla:na8na%2Bnlay%26aona0--anbs@rdsbroker-testfree-nonprod-1-eu-west-1.asdbjasdg.eu-west-1.rds.amazonaws.com:5432/dbuajsdhkasdhaks",
     "username": "ua98s7%3Fananla"
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

    def test_rds_testfree_postgres(self):
        os.environ["VCAP_SERVICES"] = self.rds_vcap_example

        factory = DatabaseConfigurationFactory()

        config = factory.get_instance().get_m2ee_configuration()
        assert config["DatabaseType"] == "PostgreSQL"
        assert (
            config["DatabaseHost"]
            == "rdsbroker-testfree-nonprod-1-eu-west-1.asdbjasdg.eu-west-1.rds.amazonaws.com:5432"  # noqa: E501
        )
        assert config["DatabaseName"] == "dbuajsdhkasdhaks"
        assert config["DatabaseJdbcUrl"].find("tcpKeepAlive") >= 0

    def test_rds_testfree_postgres_urlencoded(self):
        os.environ["VCAP_SERVICES"] = self.urlencoded_rds_vcap_example

        factory = DatabaseConfigurationFactory()

        config = factory.get_instance().get_m2ee_configuration()
        assert config["DatabaseType"] == "PostgreSQL"
        assert (
            config["DatabaseHost"]
            == "rdsbroker-testfree-nonprod-1-eu-west-1.asdbjasdg.eu-west-1.rds.amazonaws.com:5432"  # noqa: E501
        )
        assert config["DatabaseName"] == "dbuajsdhkasdhaks"
        assert config["DatabaseJdbcUrl"].find("tcpKeepAlive") >= 0
        assert config["DatabaseUserName"] == "ua98s7?ananla"
        assert config["DatabasePassword"] == "na8na+nlay&aona0--anbs"
