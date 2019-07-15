import json
import os
import urllib.parse

from database_config import (
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
                    "host": "hostname.region.subdomain.domain",
                    "password": "password",
                    "port": "21863",
                    "schema": "USR_username",
                    "url": "jdbc:sap://hostname.region.subdomain.domain:21863?encrypt=true\u0026validateCertificate=true\u0026currentschema=USR_username",
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
        expected_query_params = {
            "encrypt": ["true"],
            "validateCertificate": ["true"],
            "currentschema": ["USR_username"],
        }
        vcap = json.loads(self.sap_hana_vcap_example)

        sapHanaConfiguration = SapHanaDatabaseConfiguration(
            vcap["hana"][0]["credentials"]
        )
        config = sapHanaConfiguration.get_m2ee_configuration()
        assert (
            "hostname.region.subdomain.domain:21863" == config["DatabaseHost"]
        ), "hostname mismatch. got: {}".format(config["DatabaseHost"])
        assert "DatabaseJdbcUrl" in config
        split_url = urllib.parse.urlsplit(config["DatabaseJdbcUrl"])
        assert "jdbc" == split_url.scheme
        assert "" == split_url.netloc
        assert "sap://hostname.region.subdomain.domain:21863" == split_url.path

        queryparams = urllib.parse.parse_qs(split_url.query)
        assert expected_query_params == queryparams

    def test_sap_hana_extra_params(self):
        expected_query_params = {
            "encrypt": ["true"],
            "validateCertificate": ["true"],
            "currentschema": ["USR_username"],
            "foo": ["bar"],
        }
        os.environ["DATABASE_CONNECTION_PARAMS"] = json.dumps({"foo": "bar"})
        vcap = json.loads(self.sap_hana_vcap_example)

        sapHanaConfiguration = SapHanaDatabaseConfiguration(
            vcap["hana"][0]["credentials"]
        )
        config = sapHanaConfiguration.get_m2ee_configuration()
        assert "DatabaseJdbcUrl" in config

        split_url = urllib.parse.urlsplit(config["DatabaseJdbcUrl"])
        assert "jdbc" == split_url.scheme
        assert "" == split_url.netloc
        assert "sap://hostname.region.subdomain.domain:21863" == split_url.path

        queryparams = urllib.parse.parse_qs(split_url.query)
        assert expected_query_params == queryparams
