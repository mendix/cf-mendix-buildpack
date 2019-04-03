import os
from database_config import DatabaseConfigurationFactory

# IMPORTANT: to run this test successfully you need to set PYTHONPATH before
# running nosetest.
# export PYTHONPATH=<buildpack-root>/lib


class TestCaseMySQLDryRun:

    rds_vcap_example = """
{
  "other-mysql-ota": [
   {
    "binding_name": null,
    "credentials": {
     "hostname": "mysql.domain.local",
     "jdbcUrl": "jdbc:mysql://mysql.domain.local:3306/cf_databasename?user=xx\u0026password=yy",
     "name": "cf_databasename",
     "password": "yy",
     "port": 3306,
     "uri": "mysql://xx:yy@mysql.domain.local:3306/cf_databasename?reconnect=true",
     "username": "xx"
    },
    "instance_name": "acceptance-app-db",
    "label": "other-mysql-ota",
    "name": "acceptance-app-db",
    "plan": "20gb",
    "provider": null,
    "syslog_drain_url": null,
    "tags": [
     "mysql"
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
        assert config["DatabaseType"] == "MySQL"
        assert config["DatabaseHost"] == "mysql.domain.local:3306"
        assert config["DatabaseName"] == "cf_databasename"
        assert config["DatabaseUserName"] == "xx"
        assert config["DatabasePassword"] == "yy"
