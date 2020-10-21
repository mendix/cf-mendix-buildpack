from buildpack.databroker.config_generator.scripts.generators.debezium_configs.debezium_interface import (
    DebeziumInterface,
)


class DebeziumDefault(DebeziumInterface):
    def __init__(self, dbz_generators):
        config_generator = next(
            (idx for idx in dbz_generators if idx.is_generator()), None
        )
        if config_generator is not None:
            self.config_generator = config_generator
        else:
            self.config_generator = self

    def is_generator(self) -> bool:
        return True

    def generate_config(self) -> dict:
        if self.config_generator != self:
            return self.config_generator.generate_config()
        else:
            return {}
