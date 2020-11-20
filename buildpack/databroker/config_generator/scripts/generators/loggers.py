from buildpack.databroker.config_generator.scripts.utils import (
    template_engine_instance,
)


def generate_kafka_connect_logging_config(config):
    env = template_engine_instance()
    template = env.get_template("logging/debezium-log4j.properties")
    return template.render(config)
