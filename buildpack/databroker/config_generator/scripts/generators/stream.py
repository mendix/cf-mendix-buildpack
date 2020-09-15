from buildpack.databroker.config_generator.scripts.utils import (
    template_engine_instance,
)


def generate_config(config):
    env = template_engine_instance()
    template = env.get_template("streaming_producer.json")
    return template.render(config)
