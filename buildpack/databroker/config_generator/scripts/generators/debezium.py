from buildpack.databroker.config_generator.scripts.generators.debezium_configs.debezium_interface import (  # noqa: C0301
    DebeziumInterface,
)
from buildpack.databroker.config_generator.scripts.generators.debezium_configs.debezium_default import (  # noqa: C0301
    DebeziumDefault,
)

# Do not remove this import, it allows automatic class load
from buildpack.databroker.config_generator.scripts.generators.debezium_configs import *  # noqa: C0301, F403


def generate_config(config):
    subclasses = [
        cls(config)
        for cls in filter(
            lambda x: x != DebeziumDefault, DebeziumInterface.__subclasses__()
        )
    ]
    config_generator = DebeziumDefault(subclasses)
    debezium_config = config_generator.generate_config()

    return debezium_config
