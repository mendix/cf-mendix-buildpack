import json
import os
import unittest

from buildpack.databroker import connect, streams
from buildpack.databroker.config_generator.scripts.configloader import (
    configinitializer,
)
from buildpack.databroker.config_generator.scripts.utils import write_file

# Constants
TEST_METADATA_FILE_PATH = "/tmp/metadata.json"
TEST_DEPENDENCIES_FILE_PATH = "/tmp/dependencies.json"
TEST_BROKER_URL = "broker:29092"

LOCAL_DATABROKER_FOLDER = "{}/.local/databroker".format(os.getcwd())
KAFKA_CONNECT_DIR = "{}/kafka-connect".format(LOCAL_DATABROKER_FOLDER)
KAFKA_CONNECT_CFG_NAME = "connect.properties"
KAFKA_CONNECT_CFG_PATH = "{}/{}".format(
    KAFKA_CONNECT_DIR, KAFKA_CONNECT_CFG_NAME
)

STREAM_SIDECAR_DIR = "{}/producer-streams/stream-sidecar-0.18.0".format(
    LOCAL_DATABROKER_FOLDER
)
STREAM_TOPOLOGY_CFG_NAME = "topology.conf"
STREAM_TOPOLOGY_CFG_PATH = "{}/{}".format(
    STREAM_SIDECAR_DIR, STREAM_TOPOLOGY_CFG_NAME
)
STREAM_AZKARRA_DIR = "{}/azkarra".format(LOCAL_DATABROKER_FOLDER)
STREAM_AZKARRA_CFG_NAME = "azkarra.conf"
STREAM_AZKARRA_CFG_PATH = "{}/{}".format(
    STREAM_AZKARRA_DIR, STREAM_AZKARRA_CFG_NAME
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
            "objectName": "MyFirstModule.company",
            "topicName": "bde821e1-f8cf-43c3-9c49-8af49bebb084.16747dc6-b6b7-42ae-aabf-255dca2aeeaf.56f74de7-32c5-48c9-8157-7df3670896db.1_0_0"
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

    # There are two configs for streams, one is topology.conf another is azkarra.conf
    # Make sure specifice fields would be replaced with correct value based on template file
    def test_stream_config(self):

        self._check_folder_exist(STREAM_SIDECAR_DIR)
        self._check_folder_exist(STREAM_AZKARRA_DIR)

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
                ][0]["entities"][0]["objectName"]
            )
            assert (
                actual_config["topologies"][0]["source"]
                == "mendix.public.myfirstmodule_company"
            )
            assert (
                actual_config["topologies"][0]["sink"]
                == expect_metadata_config["DataBrokerConfiguration"][
                    "publishedServices"
                ][0]["entities"][0]["topicName"]
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
