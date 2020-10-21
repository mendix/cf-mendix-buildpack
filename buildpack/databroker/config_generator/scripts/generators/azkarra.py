from buildpack.databroker.config_generator.scripts.utils import (
    template_engine_instance,
)
from omegaconf import OmegaConf


def generate_config(config):
    env = template_engine_instance()
    template = env.get_template("azkarra.conf")
    azkarra_component_paths = (
        OmegaConf.select(config, "azkarra.component.paths") or None
    )
    azkarra_home = OmegaConf.select(config, "azkarra.home") or None
    broker_password = OmegaConf.select(config, "broker.password") or None
    broker_username = OmegaConf.select(config, "broker.username") or None
    return template.render(
        config,
        azkarra_component_paths=azkarra_component_paths,
        azkarra_home=azkarra_home,
        broker_password=broker_password,
        broker_username=broker_username,
    )
