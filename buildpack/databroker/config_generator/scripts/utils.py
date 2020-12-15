from jinja2 import Environment, FileSystemLoader
from functools import reduce
from omegaconf import OmegaConf
from buildpack.databroker.config_generator.scripts.constants import (
    METADATA_CONSTANTS,
)


def write_file(output_file_path, content):
    if output_file_path is None:
        print(content)
    else:
        try:
            with open(output_file_path, "w") as f:
                f.write(str(content))
        except Exception as exception:
            raise Exception(
                "Error while trying to write the configuration to a file. Reason: '{}'".format(
                    exception
                )
            )


def template_engine_instance(
    path="buildpack/databroker/config_generator/templates",
):
    return Environment(loader=FileSystemLoader(path))


def convert_dot_field_to_dict(field):
    output = {}
    if type(field) is dict:
        for key, value in field.items():
            path = key.split(".")
            target = reduce(
                lambda d, k: d.setdefault(k, {}), path[:-1], output
            )
            target[path[-1]] = convert_dot_field_to_dict(value)
        return output
    else:
        return field


def get_value_for_constant(conf, key):
    return OmegaConf.select(conf, "{}.{}".format(METADATA_CONSTANTS, key))
