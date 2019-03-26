import json
import os
from databaseconfig import (
    DatabaseConfigurationFactory,
    SapHanaDatabaseConfiguration,
)


# IMPORTANT: to run this test successfully you need to set PYTHONPATH before
# running nosetest.
# export PYTHONPATH=<buildpack-root>/lib


class TestCaseSapHanaDryRun:

    sap_hana_vcap_example = """
{
        "hana": [
            {
                "binding_name": null,
                "credentials": {
                    "certificate": "-----BEGIN CERTIFICATE-----\\n<<certficate>>\\n-----END CERTIFICATE-----\\n",
                    "driver": "com.sap.db.jdbc.Driver",
                    "host": "hostname",
                    "password": "password",
                    "port": "21863",
                    "schema": "USR_username",
                    "url": "jdbc:sap://hostname:21863?encrypt=true\u0026validateCertificate=true\u0026currentschema=USR_username",
                    "user": "USR_username"
                },
                "instance_name": "Hana Schema",
                "label": "hana",
                "name": "Hana Schema",
                "plan": "schema",
                "provider": null,
                "syslog_drain_url": null,
                "tags": [
                    "hana",
                    "database",
                    "relational"
                ],
                "volume_mounts": []
            }
        ]
}
    """  # noqa

    def test_sap_hana_selection(self):
        os.environ["VCAP_SERVICES"] = self.sap_hana_vcap_example

        factory = DatabaseConfigurationFactory()
        assert factory.present_in_vcap("hana") is not None
        assert factory.present_in_vcap(
            "hana", tags=["hana", "database", "relational"]
        )
        assert factory.present_in_vcap(
            None, tags=["hana", "database", "relational"]
        )

        assert factory.get_instance().database_type == "SAPHANA"

    def test_sap_hana(self):
        vcap = json.loads(self.sap_hana_vcap_example)

        sapHanaConfiguration = SapHanaDatabaseConfiguration(
            vcap["hana"][0]["credentials"]
        )
        config = sapHanaConfiguration.get_database_configuration()
        assert "DatabaseJdbcUrl" in config
        assert (
            config["DatabaseJdbcUrl"]
            == "jdbc:sap://hostname:21863?encrypt=true\u0026validateCertificate=true\u0026currentschema=USR_username"
        ), "url mismatch: {}".format(
            config["DatabaseJdbcUrl"]
        )

    def test_sap_hana_extra_params(self):
        os.environ["DATABASE_CONNECTION_PARAMS"] = json.dumps({"foo": "bar"})
        vcap = json.loads(self.sap_hana_vcap_example)

        sapHanaConfiguration = SapHanaDatabaseConfiguration(
            vcap["hana"][0]["credentials"]
        )
        config = sapHanaConfiguration.get_database_configuration()
        assert "DatabaseJdbcUrl" in config
        assert (
            config["DatabaseJdbcUrl"]
            == "jdbc:sap://hostname:21863?encrypt=true\u0026validateCertificate=true\u0026currentschema=USR_username\u0026foo=bar"  # noqa: E501
        ), "url mismatch: {}".format(
            config["DatabaseJdbcUrl"]
        )
