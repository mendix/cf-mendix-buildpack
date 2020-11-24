from buildpack.databroker.config_generator.scripts.utils import (
    template_engine_instance,
)
from buildpack.databroker.config_generator.scripts.constants import (
    JAVA_BIN_PATH,
)


def generate_kafka_connect_jmx_config():
    env = template_engine_instance()
    template = env.get_template("jmx/kafka-connect.yaml.j2")
    return template.render(java_path=JAVA_BIN_PATH)


def generate_kafka_streams_jmx_config():
    env = template_engine_instance()
    template = env.get_template("jmx/kafka-streams.yaml.j2")
    return template.render(java_path=JAVA_BIN_PATH)
