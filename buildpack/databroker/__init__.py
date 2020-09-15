#
# [EXPERIMENTAL]
#
# Add databroker components to an mx app container
#

import os
import logging
import json

from buildpack.databroker import connect, streams
from buildpack.databroker.config_generator.scripts.configloader import (
    configinitializer,
)

DATABROKER_ENABLED_FLAG = "DATABROKER_ENABLED"
RUNTIME_DATABROKER_FLAG = "DATABROKER.ENABLED"

APP_MODEL_HOME = "/home/vcap/app/model"
METADATA_FILE = os.path.join(APP_MODEL_HOME, "metadata.json")
DEP_FILE = os.path.join(APP_MODEL_HOME, "dependencies.json")

MAX_DATABROKER_COMPONENT_RESTART_RETRIES = 4


def is_enabled():
    if os.environ.get(DATABROKER_ENABLED_FLAG) == "true":
        logging.debug("Databroker is enabled")
        return True
    else:
        return False


def is_producer_app():
    if not is_enabled():
        return False

    with open(METADATA_FILE) as f:
        metadata_json = json.load(f)

    db_config = metadata_json.get("DataBrokerConfiguration")
    if (
        db_config != None
        and db_config.get("publishedServices") != None
        and len(db_config.get("publishedServices")) > 0
    ):
        return True
    else:
        return False


def should_run_kafka_connect():
    try:
        if (
            os.environ["CF_INSTANCE_INDEX"] != None
            and int(os.environ["CF_INSTANCE_INDEX"]) == 0
        ):
            return True
        else:
            return False
    except:
        return False


def stage(install_path, cache_dir):
    if not is_enabled():
        return

    connect.stage(install_path, cache_dir)
    streams.stage(install_path, cache_dir)


class Databroker:
    def __init__(self):
        self.kafka_connect = None
        self.kafka_streams = None
        self.restart_retries = 0
        self.is_producer_app = is_producer_app()

    def __setup_configs(self, database_config):
        metadata = open(METADATA_FILE, "rt")
        dep = open(DEP_FILE, "rt")
        complete_conf = configinitializer.unify_configs(
            [metadata, dep], database_config
        )
        metadata.close()
        dep.close()
        return complete_conf

    def run(self, m2ee_client, database_config):
        if not self.is_producer_app:
            return
        logging.info("Databroker: Initializing components")

        try:
            logging.info(
                "Databroker: Waiting for database initialization to complete"
            )
            if not m2ee_client.ping(timeout=30):
                raise Exception(
                    "Failed to receive successful ping from admin api"
                )
            logging.info(
                "Databroker: database is now available, starting broker components"
            )

            complete_conf = self.__setup_configs(database_config)
            if should_run_kafka_connect():
                self.kafka_connect = connect.run(complete_conf)
            self.kafka_streams = streams.run(complete_conf)
            logging.info("Databroker: Initialization complete")
        except Exception as ex:
            logging.error(
                "Databroker: Initialization failed due to {}".format(ex)
            )
            raise Exception("Databroker initailization failed") from ex

    def stop(self):
        if not self.is_producer_app:
            return

        if self.kafka_connect:
            self.kafka_connect.stop()

        if self.kafka_streams:
            self.kafka_streams.stop()

    def kill(self):
        if not self.is_producer_app:
            return
        if self.kafka_connect:
            self.kafka_connect.kill()
        if self.kafka_streams:
            self.kafka_streams.kill()

    def restart_if_any_component_not_healthy(self):
        if not self.is_producer_app:
            return True

        if self.restart_retries > MAX_DATABROKER_COMPONENT_RESTART_RETRIES:
            logging.error(
                "Databroker: component restart retries exhaused. Stopping the app"
            )
            return False

        if self.kafka_connect and not self.kafka_connect.is_alive():
            self.kafka_connect.restart()
            self.restart_retries += 1
        if self.kafka_streams and not self.kafka_streams.is_alive():
            self.kafka_streams.restart()
            self.restart_retries += 1

        return True
