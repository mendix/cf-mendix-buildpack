import socket
import re

import backoff

from . import basetest
from .runner import CfLocalRunnerWithPostgreSQL

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


class CfLocalRunnerWithKafka(CfLocalRunnerWithPostgreSQL):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._database_postgres_image = POSTGRES_DB_DOCKER_IMAGE
        self._database_postgres_version = POSTGRES_DB_VERSION

        self._kafka_container_name = "{}-{}".format(
            self._app_name, KAFKA_CLUSTER_NAME
        )

    def _get_environment(self, env_vars):
        environment = super()._get_environment(env_vars)

        environment.update(
            {
                "MX_MyFirstModule_broker_url": "{}:{}".format(
                    self.get_host(),
                    KAFKA_BROKER_PORT,
                )
            }
        )

        return environment

    def _start_kafka_cluster(self):
        result = self._cmd(
            (
                "docker",
                "run",
                "--name",
                self._kafka_container_name,
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

    def stage(self, *args, **kwargs):
        result = super().stage(*args, **kwargs)

        self._start_kafka_cluster()

        @backoff.on_predicate(backoff.expo, lambda x: x > 0, max_time=30)
        def _await_kafka_cluster():
            return socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            ).connect_ex(("localhost", KAFKA_BROKER_PORT))

        _await_kafka_cluster()

        return result

    def is_debezium_running(self):
        return self.run_on_container("curl " + KAFKA_PG_CONNECTOR_STATUS_API)

    def is_azkarra_running(self):
        topics = self.run_on_container(
            "./opt/kafka_2.12-{}/bin/kafka-topics.sh --list --zookeeper localhost:{}".format(
                KAFKA_CLUSTER_IMAGE_VERSION,
                KAFKA_ZOOKEEPER_PORT,
            ),
            target_container=self._kafka_container_name,
        )

        expect_public_topic_pattern = r".*?\.{}".format(
            DATABROKER_TOPIC_FORMAT_VERSION
        )

        return (
            len(
                re.findall(
                    r"(mx-databroker-connect-(?:configs|offsets|status))",
                    topics,
                )
            )
            == 3
            and len(re.findall(expect_public_topic_pattern, topics)) > 0
        )


class TestCaseDataBroker(basetest.BaseTestWithPostgreSQL):
    def _init_cflocal_runner(self, *args, **kwargs):
        return CfLocalRunnerWithKafka(*args, **kwargs)

    def test_databroker_running(self):
        # os.environ[
        #     "PACKAGE_URL"
        # ] = "https://dghq119eo3niv.cloudfront.net/test-app/MyProducer902.mda"
        self.stage_container(
            package="https://dghq119eo3niv.cloudfront.net/test-app/MyProducer902.mda",
            env_vars={
                "DATABROKER_ENABLED": "true",
                "FORCED_MXRUNTIME_URL": "https://dghq119eo3niv.cloudfront.net/",
            },
        )

        self.start_container()

        # check app is running
        self.assert_app_running()

        @backoff.on_exception(
            backoff.constant,
            Exception,
            interval=BACKOFF_TIME,
            max_tries=MAX_RETRY_COUNT,
        )
        def check_if_dbz_running():
            return self._runner.is_debezium_running()

        response = check_if_dbz_running()
        assert str(response).find('"state":"RUNNING"') > 0

        # check azkarra is running by verify expected topics have been created
        assert self._runner.is_azkarra_running()

        # check streaming service
        output = self.get_recent_logs()
        assert output is not None
        assert (
            str(output).find("State transition from REBALANCING to RUNNING")
            >= 0
        )
