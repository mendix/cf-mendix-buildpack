import socket
import re
import os

import backoff

from tests.integration import basetest

# Constants
KAFKA_CLUSTER_IMAGE_NAME = "johnnypark/kafka-zookeeper"
KAFKA_CLUSTER_IMAGE_VERSION = "2.4.0"
KAFKA_CLUSTER_NAME = "kafka-cluster"
KAFKA_CONNECT_URL = "http://localhost:8083"
KAFKA_PG_CONNECTOR_NAME = "mx-databroker-PostgreSQL-source-connector"
KAFKA_PG_CONNECTOR_STATUS_API = "{}/connectors/{}/status".format(
    KAFKA_CONNECT_URL,
    KAFKA_PG_CONNECTOR_NAME,
)
KAFKA_BROKER_PORT = 9092
KAFKA_ZOOKEEPER_PORT = 2181
DATABROKER_TOPIC_FORMAT_VERSION = "1_0_0"
POSTGRES_DB_DOCKER_IMAGE = "debezium/postgres"
POSTGRES_DB_VERSION = "9.6-alpine"
MAX_RETRY_COUNT = 8
BACKOFF_TIME = 10


class TestCaseDataBroker(basetest.BaseTestWithPostgreSQL):

    kafka_container_name = None

    def _start_kafka_cluster(self):
        result = self._cmd(
            (
                "docker",
                "run",
                "--name",
                self.kafka_container_name,
                "-p",
                "{}:{}".format(KAFKA_BROKER_PORT, KAFKA_BROKER_PORT),
                "-e",
                "ADVERTISED_HOST={}".format(self._host),
                "-e",
                "NUM_PARTITIONS={}".format(3),
                "-d",
                "{}:{}".format(
                    KAFKA_CLUSTER_IMAGE_NAME,
                    KAFKA_CLUSTER_IMAGE_VERSION,
                ),
            )
        )

        if not result[1]:
            raise RuntimeError(
                "Cannot create {} container: {}".format(
                    KAFKA_CLUSTER_NAME,
                    result[0],
                )
            )

    def _start_databroker_containers(self):
        @backoff.on_predicate(backoff.expo, lambda x: x > 0, max_time=30)
        def _await_kafka_cluster():
            return socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            ).connect_ex(("localhost", KAFKA_BROKER_PORT))

        _await_kafka_cluster()

        self.start_container()

    def tearDown(self):
        self._remove_container(self.kafka_container_name)
        super().tearDown()

    def test_databroker_running(self):
        # change the default db image
        self._database_postgres_image = POSTGRES_DB_DOCKER_IMAGE
        self._database_postgres_version = POSTGRES_DB_VERSION

        # start local kafka cluster
        self.kafka_container_name = "{}-{}-{}".format(
            self._get_prefix(), self._app_id, KAFKA_CLUSTER_NAME
        )
        self._start_kafka_cluster()

        os.environ[
            "PACKAGE_URL"
        ] = "https://dghq119eo3niv.cloudfront.net/test-app/MyProducer902.mda"
        self.stage_container(
            "ProducerApp.mda",
            env_vars={
                "DATABROKER_ENABLED": "true",
                "FORCED_MXRUNTIME_URL": "https://dghq119eo3niv.cloudfront.net/",
                "MXRUNTIME_DatabaseType": "PostgreSQL",
                "MXRUNTIME_DatabaseHost": "{}:{}".format(
                    self._host, self._database_port
                ),
                "MXRUNTIME_DatabaseName": "test",
                "MXRUNTIME_DatabaseUserName": "test",
                "MXRUNTIME_DatabasePassword": "test",
                "MX_MyFirstModule_broker_url": "{}:{}".format(
                    self._host,
                    KAFKA_BROKER_PORT,
                ),
            },
        )

        self._start_databroker_containers()

        # check app is running
        self.assert_app_running()

        @backoff.on_exception(
            backoff.constant,
            Exception,
            interval=BACKOFF_TIME,
            max_tries=MAX_RETRY_COUNT,
        )
        def check_if_dbz_running():
            return self.run_on_container(
                "curl " + KAFKA_PG_CONNECTOR_STATUS_API
            )

        response = check_if_dbz_running()
        assert str(response).find('"state":"RUNNING"') > 0

        # check azkarra is running by verify expected topics have been created
        topics = self.run_on_container(
            "./opt/kafka_2.12-{}/bin/kafka-topics.sh --list --zookeeper localhost:{}".format(
                KAFKA_CLUSTER_IMAGE_VERSION,
                KAFKA_ZOOKEEPER_PORT,
            ),
            target_container=self.kafka_container_name,
        )
        assert (
            len(
                re.findall(
                    r"(mx-databroker-connect-(?:configs|offsets|status))",
                    topics,
                )
            )
            == 3
        )

        expect_public_topic_pattern = r".*?\.{}".format(
            DATABROKER_TOPIC_FORMAT_VERSION
        )

        assert len(re.findall(expect_public_topic_pattern, topics)) > 0

        # check streaming service
        output = self.get_recent_logs()
        assert output is not None
        assert (
            str(output).find("State transition from REBALANCING to RUNNING")
            >= 0
        )
