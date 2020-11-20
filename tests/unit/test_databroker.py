import json
import os
import unittest
from pathlib import Path

from buildpack.databroker import connect, streams
from buildpack.databroker.config_generator.scripts.configloader import (
    configinitializer,
)
from buildpack.databroker.config_generator.scripts.utils import write_file

from buildpack.databroker.config_generator.scripts.generators import (
    debezium as debezium_generator,
)

# Constants
TEST_METADATA_FILE_PATH = "/tmp/metadata.json"
TEST_DEPENDENCIES_FILE_PATH = "/tmp/dependencies.json"
TEST_BROKER_URL = "localhost:9092"

LOCAL_DATABROKER_FOLDER = "{}/.local/databroker".format(os.getcwd())
KAFKA_CONNECT_DIR = "{}/kafka-connect".format(LOCAL_DATABROKER_FOLDER)
KAFKA_CONNECT_CFG_NAME = "connect.properties"
KAFKA_CONNECT_CFG_PATH = "{}/{}".format(
    KAFKA_CONNECT_DIR, KAFKA_CONNECT_CFG_NAME
)
LOG4J_DEBEZIUM_CFG_PATH = "{}/{}".format(
    KAFKA_CONNECT_DIR, "debezium-log4j.properties"
)

STREAM_SIDECAR_DIR = "{}/producer-streams/stream-sidecar-{}".format(
    LOCAL_DATABROKER_FOLDER, streams.get_pdr_stream_version()
)
STREAM_TOPOLOGY_CFG_NAME = "topology.conf"
STREAM_TOPOLOGY_CFG_PATH = "{}/{}".format(
    STREAM_SIDECAR_DIR, STREAM_TOPOLOGY_CFG_NAME
)
STREAM_AZKARRA_CFG_NAME = "azkarra.conf"
STREAM_AZKARRA_CFG_PATH = "{}/{}".format(
    STREAM_SIDECAR_DIR, STREAM_AZKARRA_CFG_NAME
)


class TestDataBrokerConfigs(unittest.TestCase):
    complete_producer_conf = None

    # define metadata config
    metadata_config = """
{
  "Constants": [
    {
      "Name": "MyFirstModule.Kafka_broker_url",
      "Type": "String",
      "Description": "",
      "DefaultValue": "localhost:9092"
    },
    {
      "Name": "Atlas_UI_Resources.Atlas_UI_Resources_Version",
      "Type": "String",
      "Description": "",
      "DefaultValue": " 2.5.4"
    }
  ],
  "ScheduledEvents": [],
  "DataBrokerConfiguration": {
    "publishedServices": [
      {
        "brokerUrl": "MyFirstModule.Kafka_broker_url",
        "entities": [
          {
            "originalEntityName": "MyFirstModule.company",
            "publicEntityName": "MyFirstModule.company",
            "topicName": "bde821e1-f8cf-43c3-9c49-8af49bebb084.16747dc6-b6b7-42ae-aabf-255dca2aeeaf.56f74de7-32c5-48c9-8157-7df3670896db.1_0_0",
            "attributeMapping": {
              "INT_CompanyName": "CompanyName",
              "INT_CompanyId": "CompanyId",
              "INT_CompanyAddress": "INT_CompanyAddress"
            }
          },
          {
            "originalEntityName": "MyFirstModule.project",
            "publicEntityName": "MyFirstModule.projectPublic",
            "topicName": "bde821ec-f8cf-43cc-9c4c-8af49bebb08c.16747dcc-b6bc-42ac-aabc-255dca2aeeac.56f74dec-32cc-48cc-8157-7df3670896dc.1_0_0",
            "attributeMapping": {
              "INT_ProjectName": "ProjectName",
              "INT_ProjectId": "ProjectId",
              "INT_ProjectAddress": "INT_ProjectAddress"
            }
          }
        ]
      },
      {
        "brokerUrl": "MyFirstModule.Kafka_broker_url",
        "entities": [
          {
            "originalEntityName": "MyFirstModule.companyint",
            "publicEntityName": "MyFirstModule.companypub",
            "topicName": "bde821ed-f8cd-43c3-9c4d-8af49bebb08d.16747dcd-b6bd-42ad-aabd-255dca2aeead.56f74ded-32cd-48cd-815d-7df3670896dd.1_0_0",
            "attributeMapping": {
              "INT_CompanyPubName": "CompanyPubName",
              "INT_CompanyPubId": "CompanyPubId",
              "INT_CompanyPubAddress": "INT_CompanyPubAddress"
            }
          },
          {
            "originalEntityName": "MyFirstModule.member",
            "publicEntityName": "MyFirstModule.memberpub",
            "topicName": "bde821ee-f8ce-43ce-9c4e-8af49bebb08e.16747dce-b6be-42ae-aabe-255dca2aeeae.56f74dee-32ce-48ce-815e-7df3670896de.1_0_0",
            "attributeMapping": {
              "INT_MemberPubName": "MemberPubName",
              "INT_MemberPubId": "MemberPubId",
              "INT_MemberPubAddress": "INT_MemberPubAddress"
            }
          }
        ]
      }
    ]
  }
}
"""
    # define dependencies config
    dependencies_config = """
{
  "schemaVersion": "0.2",
  "appName": "Simple-Producer-App",
  "published": [],
  "consumed": []
}
"""

    def setUp(self):

        # transform string to file mode
        write_file(TEST_METADATA_FILE_PATH, self.metadata_config)
        write_file(TEST_DEPENDENCIES_FILE_PATH, self.dependencies_config)

        # define environment variables
        os.environ["MXRUNTIME_DatabaseType"] = "PostgreSQL"
        os.environ["MXRUNTIME_DatabaseHost"] = "localhost:5432"
        os.environ["MXRUNTIME_DatabaseUserName"] = "mx-app"
        os.environ["MXRUNTIME_DatabaseName"] = "mendix"
        os.environ["MXRUNTIME_DatabasePassword"] = "mx-app-password"
        # environment variable will overwrite the defautl constant value
        os.environ["MX_MyFirstModule.Kafka_broker_url"] = TEST_BROKER_URL

        metadata_file = open(TEST_METADATA_FILE_PATH, "rt")
        dependencies_file = open(TEST_DEPENDENCIES_FILE_PATH, "rt")

        database_config = {}
        self.complete_producer_conf = configinitializer.unify_configs(
            [metadata_file, dependencies_file], database_config
        )

        metadata_file.close()
        dependencies_file.close()

    def tearDown(self):
        os.unlink(TEST_METADATA_FILE_PATH)
        os.unlink(TEST_DEPENDENCIES_FILE_PATH)

    def _check_folder_exist(self, folder_path):
        os.makedirs(folder_path, exist_ok=True)

    def test_kafka_connect_config(self):

        self._check_folder_exist(KAFKA_CONNECT_DIR)

        # check config has been generated
        connect.setup_configs(self.complete_producer_conf)

        assert os.path.isfile(KAFKA_CONNECT_CFG_PATH)

        actual_config = {}
        with open(KAFKA_CONNECT_CFG_PATH, "r") as f:
            for line in f.readlines():
                tmp_line = line.strip().split("=")
                actual_config[tmp_line[0]] = tmp_line[1]

            assert actual_config["bootstrap.servers"] == os.environ.get(
                "MX_MyFirstModule.Kafka_broker_url"
            )

        # verify postgres whitelists
        debezium_config = json.loads(
            debezium_generator.generate_config(self.complete_producer_conf)
        )
        assert (
            debezium_config["config"]["table.whitelist"]
            == ".*MyFirstModule.company.*,.*MyFirstModule.project.*"
        )
        assert (
            debezium_config["config"]["column.whitelist"]
            == ".*MyFirstModule.company.*,MyFirstModule.company.id,.*MyFirstModule.project.*,MyFirstModule.project.id"
        )

    def test_streams_override(self):
        os.environ["STREAMS_VERSION"] = "0.99999"
        assert streams.get_pdr_stream_version() == "0.99999"
        del os.environ["STREAMS_VERSION"]  # reset
        # default
        assert streams.get_pdr_stream_version() == "0.23.0-9"

    # There are two configs for streams, one is topology.conf another is azkarra.conf
    # Make sure specifice fields would be replaced with correct value based on template file
    def test_stream_config(self):

        self._check_folder_exist(STREAM_SIDECAR_DIR)

        streams.setup_configs(self.complete_producer_conf)

        # verify topology config
        assert os.path.isfile(STREAM_TOPOLOGY_CFG_PATH)

        expect_metadata_config = json.loads(self.metadata_config)
        with open(STREAM_TOPOLOGY_CFG_PATH, "r") as f:
            actual_config = json.loads(f.read())

            assert actual_config["topologies"][0][
                "name"
            ] == "{} topology".format(
                expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][0]["publicEntityName"]
            )
            assert (
                actual_config["topologies"][0]["source"]
                == "mendix.public.myfirstmodule_company.private"
            )
            assert (
                actual_config["topologies"][0]["sink"]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][0]["topicName"]
            )

            assert (
                actual_config["topologies"][0]["originalEntityName"]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][0]["originalEntityName"]
            )
            assert (
                actual_config["topologies"][0]["publicEntityName"]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][0]["publicEntityName"]
            )
            assert (
                actual_config["topologies"][0]["attributeMapping"][
                    "INT_CompanyName"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][0]["attributeMapping"]["INT_CompanyName"]
            )
            assert (
                actual_config["topologies"][0]["attributeMapping"][
                    "INT_CompanyId"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][0]["attributeMapping"]["INT_CompanyId"]
            )
            assert (
                actual_config["topologies"][0]["attributeMapping"][
                    "INT_CompanyAddress"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][0]["attributeMapping"]["INT_CompanyAddress"]
            )

            assert (
                actual_config["topologies"][1]["originalEntityName"]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][1]["originalEntityName"]
            )
            assert (
                actual_config["topologies"][1]["publicEntityName"]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][1]["publicEntityName"]
            )
            assert (
                actual_config["topologies"][1]["attributeMapping"][
                    "INT_ProjectName"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][1]["attributeMapping"]["INT_ProjectName"]
            )
            assert (
                actual_config["topologies"][1]["attributeMapping"][
                    "INT_ProjectId"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][1]["attributeMapping"]["INT_ProjectId"]
            )
            assert (
                actual_config["topologies"][1]["attributeMapping"][
                    "INT_ProjectAddress"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][1]["attributeMapping"]["INT_ProjectAddress"]
            )

            assert (
                actual_config["topologies"][2]["originalEntityName"]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][1]["entities"][0]["originalEntityName"]
            )
            assert (
                actual_config["topologies"][2]["publicEntityName"]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][1]["entities"][0]["publicEntityName"]
            )
            assert (
                actual_config["topologies"][2]["attributeMapping"][
                    "INT_CompanyPubName"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][1]["entities"][0]["attributeMapping"]["INT_CompanyPubName"]
            )
            assert (
                actual_config["topologies"][2]["attributeMapping"][
                    "INT_CompanyPubId"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][1]["entities"][0]["attributeMapping"]["INT_CompanyPubId"]
            )
            assert (
                actual_config["topologies"][2]["attributeMapping"][
                    "INT_CompanyPubAddress"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][1]["entities"][0]["attributeMapping"][
                    "INT_CompanyPubAddress"
                ]
            )

            assert (
                actual_config["topologies"][3]["originalEntityName"]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][1]["entities"][1]["originalEntityName"]
            )
            assert (
                actual_config["topologies"][3]["publicEntityName"]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][1]["entities"][1]["publicEntityName"]
            )
            assert (
                actual_config["topologies"][3]["attributeMapping"][
                    "INT_MemberPubName"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][1]["entities"][1]["attributeMapping"]["INT_MemberPubName"]
            )
            assert (
                actual_config["topologies"][3]["attributeMapping"][
                    "INT_MemberPubId"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][1]["entities"][1]["attributeMapping"]["INT_MemberPubId"]
            )
            assert (
                actual_config["topologies"][3]["attributeMapping"][
                    "INT_MemberPubAddress"
                ]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][1]["entities"][1]["attributeMapping"]["INT_MemberPubAddress"]
            )

        # verify azkarra config
        assert os.path.isfile(STREAM_AZKARRA_CFG_PATH)
        with open(STREAM_AZKARRA_CFG_PATH, "r") as f:
            actual_config = f.read()

            assert (
                str(actual_config).find(
                    'bootstrap.servers = "{}"'.format(
                        os.environ.get("MX_MyFirstModule.Kafka_broker_url")
                    )
                )
                > 1
            )

        # verify log4j configuration
        assert os.path.isfile(LOG4J_DEBEZIUM_CFG_PATH)
        assert (
            Path(LOG4J_DEBEZIUM_CFG_PATH)
            .read_text()
            .find("log4j.rootLogger=INFO, stdout")
            > -1
        )
