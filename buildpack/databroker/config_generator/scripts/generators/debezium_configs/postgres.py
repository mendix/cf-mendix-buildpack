from buildpack.databroker.config_generator.scripts.generators.debezium_configs.debezium_interface import (
    DebeziumInterface,
)
from buildpack.databroker.config_generator.scripts.constants import (
    POSTGRESQL_NAME,
    POSTGRESQL_DEFAULT_PORT,
)
from buildpack.databroker.config_generator.scripts.utils import (
    template_engine_instance,
)
from functools import reduce


class PostgresConfig(DebeziumInterface):
    def __init__(self, config):
        self.config = config

    def is_generator(self):
        return str(self.config.DatabaseType).lower() == POSTGRESQL_NAME

    def __parse_whitelist(self, entities):
        def create_whitelist_strings(whitelist, entity):
            t = ".*{}.*,".format(entity["originalEntityName"])
            whitelist["table"] += t
            whitelist["column"] += t + entity["originalEntityName"] + ".id,"
            return whitelist

        whitelist = reduce(
            create_whitelist_strings, entities, {"table": "", "column": ""}
        )
        whitelist["table"] = whitelist["table"][:-1]
        whitelist["column"] = whitelist["column"][:-1]

        return whitelist

    def generate_config(self):
        env = template_engine_instance()
        template = env.get_template("debezium/postgres.json.j2")
        whitelist = self.__parse_whitelist(
            self.config.DataBrokerConfiguration.publishedServices[0].entities
        )
        database_data = self.config.DatabaseHost.split(":")
        database_hostname = database_data[0]
        if len(database_data) > 1:
            # custom port provided
            database_port = database_data[1]
        else:
            # use default port
            database_port = POSTGRESQL_DEFAULT_PORT
        return template.render(
            self.config,
            table_whitelist=whitelist["table"],
            column_whitelist=whitelist["column"],
            database_hostname=database_hostname,
            database_port=database_port,
        )
