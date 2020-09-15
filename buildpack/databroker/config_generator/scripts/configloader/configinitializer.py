from omegaconf import OmegaConf
import json
import os
from buildpack.databroker.config_generator.scripts.utils import (
    convert_dot_field_to_dict,
    get_value_for_constant,
)
from buildpack.databroker.config_generator.scripts.constants import (
    ENV_VAR_RUNTIME_PREFIX,
    ENV_VAR_BROKER_PREFIX,
    CONSTANTS_ENV_VAR_PREFIX,
    BOOTSTRAP_SERVERS_KEY,
    SUPPORTED_DBS,
    POSTGRESQL_MAX_TABLE_LENGTH,
    NODE_COUNT_KEY,
)
from buildpack.databroker.config_generator.scripts.config_env_whitelist import (
    whitelist,
)


# variables generated with this method are going to have a single key of type "a.b.c" they are not nested
# this will be possible in a future version of OmegaConf
def __curate_key(key, prefix, replace_underscores=True):
    new_key = key.replace(prefix, "", 1)
    if replace_underscores:
        new_key = new_key.replace("_", ".")
    return new_key


def __generate_source_topic_names(config):
    for service in config.DataBrokerConfiguration.publishedServices:
        for entity in service.entities:
            entity.rawTopic = "{}.{}.{}".format(
                config.DatabaseName,
                "public",
                entity.objectName.replace(".", "_").lower(),
            )


def validate_config(complete_conf):
    # check supported dbs
    if not complete_conf.DatabaseType.lower() in [
        db.lower() for db in SUPPORTED_DBS
    ]:
        raise Exception(
            "{} is not supported. Supported dbs: {}".format(
                complete_conf.DatabaseType, SUPPORTED_DBS
            )
        )

    # validate objectname length & constants
    for (
        published_service
    ) in complete_conf.DataBrokerConfiguration.publishedServices:
        if not get_value_for_constant(
            complete_conf, published_service.brokerUrl
        ):
            raise Exception(
                "No Constants found for {}".format(published_service.brokerUrl)
            )
        for entity in published_service.entities:
            if len(entity.objectName) > POSTGRESQL_MAX_TABLE_LENGTH:
                raise Exception(
                    "Entity {}'s name is too long. Max length of {} supported".format(
                        entity.objectName, POSTGRESQL_MAX_TABLE_LENGTH
                    )
                )

    # check if bootstrap server is empty
    if not complete_conf.bootstrap_servers:
        raise Exception("Broker URL not specified")


def unify_configs(configs, database_config, parameters_replacement={}):
    complete_conf = load_config(
        configs, database_config, parameters_replacement
    )
    validate_config(complete_conf)
    return complete_conf


def load_config(configs, database_config, parameters_replacement):
    loaded_json = []

    for config in configs:
        try:
            tmp_json = json.loads(config.read())
        except Exception as exception:
            raise Exception(
                "Error loading input file called {}. Reason: '{}'".format(
                    config.name, exception
                )
            )
        # Special check for metadata files, if they exist the idea is to replace the
        # non existent constants with their default values
        if (
            config.name.endswith("metadata.json")
            and tmp_json["Constants"]
            and type(tmp_json["Constants"]) is list
        ):
            tmp_json["Constants"] = dict(
                map(
                    lambda constant: (
                        constant["Name"],
                        constant["DefaultValue"],
                    ),
                    tmp_json["Constants"],
                )
            )

        loaded_json.append(convert_dot_field_to_dict(tmp_json))

    modified_env_vars = OmegaConf.create()
    if database_config:
        modified_env_vars.update(database_config)

    for prefix in [ENV_VAR_RUNTIME_PREFIX, ENV_VAR_BROKER_PREFIX]:
        env_vars = dict(
            filter(
                lambda key: key[0].startswith(prefix) and key[0] in whitelist,
                dict(os.environ).items(),
            )
        )
        for key, value in env_vars.items():
            new_key = __curate_key(key, prefix)
            OmegaConf.update(modified_env_vars, new_key, value)

    # Fetch and update any constants passed as env var
    const_env_vars = dict(
        filter(
            lambda key: key[0].startswith(CONSTANTS_ENV_VAR_PREFIX),
            dict(os.environ).items(),
        )
    )
    modified_constants = OmegaConf.create({"Constants": {}})
    for key, value in const_env_vars.items():
        new_key = key.replace(CONSTANTS_ENV_VAR_PREFIX, "", 1)
        new_key = new_key.replace("_", ".", 1)
        OmegaConf.update(modified_constants.Constants, new_key, value)

    parameters_replacement_dict = OmegaConf.create()
    for key, value in parameters_replacement:
        OmegaConf.update(parameters_replacement_dict, key, value)

    try:
        complete_conf = OmegaConf.merge(
            *loaded_json,
            modified_env_vars,
            modified_constants,
            parameters_replacement_dict
        )
        bootstrap_servers = get_value_for_constant(
            complete_conf,
            complete_conf.DataBrokerConfiguration.publishedServices[
                0
            ].brokerUrl,
        )
        OmegaConf.update(
            complete_conf, BOOTSTRAP_SERVERS_KEY, bootstrap_servers
        )
        if not OmegaConf.select(complete_conf, NODE_COUNT_KEY):
            complete_conf[NODE_COUNT_KEY] = 1
        __generate_source_topic_names(complete_conf)
        return complete_conf
    except Exception as exception:
        raise Exception(
            "Error while reading input config files. Reason: '{}'".format(
                exception
            )
        )
