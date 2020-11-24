#
# [EXPERIMENTAL]
#
# Add Debezium to an app container to collect data from the DB for the Data Broker.
#

import os
import time
import logging
import json

import backoff
import requests

from buildpack import util
from buildpack.databroker.process_supervisor import DataBrokerProcess
from buildpack.databroker.config_generator.scripts.generators import (
    debezium as debezium_generator,
    kafka_connect as connect_generator,
    loggers as loggers_generator,
)
from buildpack.databroker.config_generator.scripts.utils import write_file

# Compile constants
BASE_URL = "/mx-buildpack/experimental/databroker/"
KAFKA_CONNECT_FILENAME = "kafka-connect"
KAFKA_CONNECT_VERSION = "2.13-2.5.1-v2"
DBZ_FILENAME = "debezium"
DBZ_VERSION = os.getenv("DBZ_VERSION", "1.2.0")
PKG_FILE_EXT = "tar.gz"
BASE_DIR = "databroker"
DBZ_DIR = "debezium"
PROCESS_NAME = "kafka-connect"
KAFKA_CONNECT_DIR = PROCESS_NAME
DBZ_CFG_NAME = "debezium-connector.json"
KAFKA_CONNECT_CFG_NAME = "connect.properties"
LOG4J_DEBEZIUM_CFG_NAME = "debezium-log4j.properties"

# Run constants
LOCAL = ".local"
KAFKA_CONNECT_START_PATH = os.path.join(
    LOCAL, BASE_DIR, KAFKA_CONNECT_DIR, "bin", "connect-distributed.sh"
)
KAFKA_CONNECT_CFG_PATH = os.path.join(
    LOCAL, BASE_DIR, KAFKA_CONNECT_DIR, KAFKA_CONNECT_CFG_NAME
)
LOG4J_CFG_PATH = os.path.join(
    LOCAL, BASE_DIR, KAFKA_CONNECT_DIR, LOG4J_DEBEZIUM_CFG_NAME
)
DBZ_HOME_DIR = os.path.join(LOCAL, BASE_DIR, DBZ_DIR)
CONNECT_URL = "http://localhost:8083/connectors"
INITIAL_WAIT = 15
MAX_RETRIES = 8
BACKOFF_TIME = 5
KAFKA_CONNECT_JMX_PORT = "11003"


def _download_pkgs(install_path, cache_dir):
    # Download kafka connect and debezium
    KAFKA_CONNECT_DOWNLOAD_URL = "{}{}-{}.{}".format(
        BASE_URL, KAFKA_CONNECT_FILENAME, KAFKA_CONNECT_VERSION, PKG_FILE_EXT,
    )
    util.download_and_unpack(
        util.get_blobstore_url(KAFKA_CONNECT_DOWNLOAD_URL),
        os.path.join(install_path, BASE_DIR, KAFKA_CONNECT_DIR),
        cache_dir=cache_dir,
    )

    DBZ_DOWNLOAD_URL = "{}{}-{}.{}".format(
        BASE_URL, DBZ_FILENAME, DBZ_VERSION, PKG_FILE_EXT
    )
    util.download_and_unpack(
        util.get_blobstore_url(DBZ_DOWNLOAD_URL),
        os.path.join(install_path, BASE_DIR, DBZ_DIR),
        cache_dir=cache_dir,
    )


def stage(install_path, cache_dir):
    _download_pkgs(install_path, cache_dir)


def setup_configs(complete_conf):
    connect_config = connect_generator.generate_config(complete_conf)
    write_file(KAFKA_CONNECT_CFG_PATH, connect_config)

    connect_logging = loggers_generator.generate_kafka_connect_logging_config(
        complete_conf
    )
    write_file(LOG4J_CFG_PATH, connect_logging)


def run(complete_conf):
    setup_configs(complete_conf)
    java_path = os.path.join(os.getcwd(), LOCAL, "bin")
    os.environ["PATH"] += os.pathsep + java_path
    os.environ["JMX_PORT"] = KAFKA_CONNECT_JMX_PORT
    os.environ["KAFKA_LOG4J_OPTS"] = (
        "-Dlog4j.configuration=file:"
        + os.path.join(os.getcwd(), LOG4J_CFG_PATH)
    )

    env = dict(os.environ)

    kafka_connect_process = DataBrokerProcess(
        PROCESS_NAME, (KAFKA_CONNECT_START_PATH, KAFKA_CONNECT_CFG_PATH), env,
    )

    # Wait for kafka connect to initialize and then issue a request for debezium connector
    time.sleep(INITIAL_WAIT)
    debezium_config = json.loads(
        debezium_generator.generate_config(complete_conf)
    )

    def backoff_hdlr(details):
        logging.warn(
            "Databroker: Failed to receive successful response from connect. Retrying...({}/{})".format(
                details["tries"], MAX_RETRIES
            )
        )

    def giveup_hdlr(details):
        logging.error("Databroker: Kafka Connect wait retries exhaused")
        raise Exception("Databroker: Kafka Connect failed to start")

    @backoff.on_predicate(
        backoff.constant,
        interval=BACKOFF_TIME,
        max_tries=MAX_RETRIES,
        on_backoff=backoff_hdlr,
        on_giveup=giveup_hdlr,
    )
    @backoff.on_exception(
        backoff.constant,
        Exception,
        interval=BACKOFF_TIME,
        max_tries=MAX_RETRIES,
        on_backoff=backoff_hdlr,
        on_giveup=giveup_hdlr,
    )
    def start_debezium_connector():
        return requests.put(
            "{}/{}/{}".format(CONNECT_URL, debezium_config["name"], "config"),
            json=debezium_config["config"],
        )

    start_debezium_connector()
    return kafka_connect_process
