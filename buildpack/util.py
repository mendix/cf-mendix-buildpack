import collections
import errno
import glob
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import urllib

import requests
import yaml
from jinja2 import DebugUndefined, Template


def print_all_logging_handlers():
    for k, v in logging.Logger.manager.loggerDict.items():
        print(f"+ [{str.ljust(k, 20)}] {{str(v.__class__)[8:-2])}} ")
        if not isinstance(v, logging.PlaceHolder):
            for h in v.handlers:
                print("     +++", str(h.__class__)[8:-2])


def get_vcap_services_data():
    if os.environ.get("VCAP_SERVICES"):
        return json.loads(os.environ.get("VCAP_SERVICES"))
    return {}


def get_vcap_data():
    if os.environ.get("VCAP_APPLICATION"):
        return json.loads(os.environ.get("VCAP_APPLICATION"))
    return {
        "application_uris": ["app.mendixcloud.com"],
        "application_name": "Mendix App",
    }


def get_domain():
    return get_vcap_data()["application_uris"][0].split("/")[0]


def get_hostname(add_instance_index=True):
    result = get_domain()
    cf_instance_index = os.getenv("CF_INSTANCE_INDEX")
    if cf_instance_index and add_instance_index:
        result += f"-{cf_instance_index}"
    return result


def get_app_from_domain():
    return get_domain().split(".")[0]


# Flattens a list
def _flatten(unflat_list):
    result = []
    for item in unflat_list:
        if isinstance(item, list):
            result.extend(_flatten(item))
        else:
            result.append(item)
    return result


DEPENDENCY_ARTIFACT_KEY = "artifact"
DEPENDENCY_MANAGED_KEY = "managed"
DEPENDENCY_NAME_KEY = "name"
DEPENDENCY_NAME_SEPARATOR = "."
DEPENDENCY_ALIAS_KEY = "alias"
DEPENDENCY_VERSION_KEY = "version"
DEPENDENCY_FILE = "dependencies.yml"
DO_NOT_RECURSE_FIELDS = [DEPENDENCY_ALIAS_KEY, DEPENDENCY_NAME_KEY]
CACHED_DEPENDENCIES = []


def initialize_globals():
    global CACHED_DEPENDENCIES
    CACHED_DEPENDENCIES = []


# Returns whether an object is a "variable" / literal in a dependency definition
def _is_dependency_literal(o):
    return type(o) in (int, str, float, bool)


# Renders a dependency object
def _render(
    obj,
    variables,
    fields=None,
):
    if fields is None:
        fields = [
            DEPENDENCY_ARTIFACT_KEY,
            DEPENDENCY_NAME_KEY,
            DEPENDENCY_ALIAS_KEY,
        ]
    for field in fields:
        if field in obj:
            if isinstance(obj[field], list):
                obj[field] = [__render(item, variables) for item in obj[field]]
            else:
                obj[field] = __render(obj[field], variables)
    return obj


def __render(o, variables):
    return Template(o, undefined=DebugUndefined).render(variables)


# Returns a list of external dependency objects
# Function argument is an object, typically loaded from YAML
# This function is a recursive descent parser
def __get_dependencies(obj):
    if (
        all(
            True if k in DO_NOT_RECURSE_FIELDS else _is_dependency_literal(v)
            for (k, v) in obj.items()  # noqa: C0301
        )
        and DEPENDENCY_ARTIFACT_KEY in obj
    ):
        # Leaf node found, return single artifact object
        return _render(obj, obj, DO_NOT_RECURSE_FIELDS)
    # Normal node found, recurse further
    result = []
    for key, value in obj.items():
        name = {}
        if not _is_dependency_literal(value) and key not in DO_NOT_RECURSE_FIELDS:
            # Recurse non-literals
            # If the item is a list, recurse for every item on the list
            if isinstance(value, list):
                for item in value:
                    # Recurse over the union of the parent object and item literals
                    if _is_dependency_literal(item):
                        result.append(__get_dependencies({**obj, **{key: item}}))
                    else:
                        if isinstance(item, dict):
                            for k, v in item.items():
                                # Add key-value mapping for dict object
                                result.append(
                                    __get_dependencies(
                                        {
                                            **obj,
                                            **{key: v},
                                            **{key + "_key": k},
                                        }
                                    )
                                )
                        else:
                            for subitem in item:
                                result.append(
                                    __get_dependencies({**obj, **{key: subitem}})
                                )
            # If the item is another object
            # recurse over the union of the item and the parent object literals
            else:
                name = {}
                if DEPENDENCY_NAME_KEY not in obj:
                    name = {DEPENDENCY_NAME_KEY: [key]}
                else:
                    name = {DEPENDENCY_NAME_KEY: obj[DEPENDENCY_NAME_KEY] + [key]}
                variables = {k: v for k, v in obj.items() if _is_dependency_literal(v)}
                result.append(__get_dependencies({**value, **variables, **name}))
    return result


# Flattens a dependency name
def _get_dependency_name(dependency):
    return DEPENDENCY_NAME_SEPARATOR.join(dependency[DEPENDENCY_NAME_KEY])


def _get_dependency_file_contents(file):
    with open(os.path.join(file), "r") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as exc:
            logging.error("Cannot parse dependency configuration file: %s", exc)
            return yaml.safe_load({})


# Returns a dict of dependencies from the dependency configuration file
# The dict key is composed of the key names of the YAML file, separated by a "."
def _get_dependencies(buildpack_dir):
    dependencies = _get_dependency_file_contents(
        os.path.join(buildpack_dir, DEPENDENCY_FILE)
    )
    if dependencies:
        result = _flatten(__get_dependencies(dependencies["dependencies"]))
        return {_get_dependency_name(x): x for x in result}
    return {}


# Gets a single dependency and renders
def get_dependency(dependency, overrides=None, buildpack_dir=os.getcwd()):
    if overrides is None:
        overrides = {}
    result = None
    artifacts = _get_dependencies(buildpack_dir)
    if artifacts is not None and dependency in artifacts:
        result = artifacts[dependency]
        if isinstance(overrides, dict) and len(overrides) > 0:
            result = _render(result, {**result, **overrides})
        else:
            result = _render(result, result)
    return result


BLOBSTORE_DEFAULT_URL = "https://cdn.mendix.com"
BLOBSTORE_BUILDPACK_DEFAULT_PREFIX = "/mx-buildpack/"


def get_blobstore():
    return os.environ.get("BLOBSTORE", BLOBSTORE_DEFAULT_URL)


def get_blobstore_url(filename, blobstore=get_blobstore()):
    main_url = blobstore
    if main_url[-1] == "/":
        main_url = main_url[0:-1]
    return main_url + filename


# Gets the artifact URL for a dependency
def _get_dependency_artifact_url(dependency):
    if dependency and DEPENDENCY_ARTIFACT_KEY in dependency:
        url = dependency[DEPENDENCY_ARTIFACT_KEY]
        if is_url(url):
            return url
        if url.startswith("/"):
            # Absolute path detected
            return get_blobstore_url(url)
        return get_blobstore_url(BLOBSTORE_BUILDPACK_DEFAULT_PREFIX + url)
    return None


# Deletes other versions of a given file
# Also accounts for aliases (either a string or a list of strings)
def _delete_other_versions(directory, file_name, alias=None):
    logging.debug(
        "Deleting other dependency versions than [%s] from [%s]...",
        file_name,
        directory,
    )
    expression = (
        r"^((?:[a-zA-Z]+-)+)((?:v*[0-9]+\.?)+.*)(\.(?:tar|tar\.gz|tgz|zip|jar))$"
    )
    patterns = [re.sub(expression, "\\1*\\3", file_name)]
    if alias:
        if isinstance(alias, str):
            alias = [alias]
        for a in alias:
            patterns.append(f"{a}-*.*")

    for pattern in patterns:
        logging.debug("Finding files matching [{}]...".format(pattern))
        files = glob.glob(f"{directory}/{pattern}")

        for f in files:
            if os.path.basename(f) != file_name:
                logging.debug(
                    "Deleting version [%s] from [%s]...", os.path.basename(f), directory
                )
                os.remove(f)


def _find_file_in_directory(file_name, directory):
    paths = [
        a
        for a in [
            os.path.abspath(p)
            for p in glob.glob(f"{directory}/**/{file_name}", recursive=True)
        ]
        if os.path.isfile(a)
    ]

    if len(paths) > 0:
        return paths[0]
    return None


# Resolves a dependency: fetches it and copies it to the specified location
# Dependency can be either a string (dependency name) or a dependency object
# retrieved with get_dependency()
def resolve_dependency(
    dependency,
    destination,
    buildpack_dir,
    cache_dir="/tmp/downloads",
    ignore_cache=False,
    unpack=True,
    unpack_strip_directories=False,
    overrides=None,
):
    if overrides is None:
        overrides = {}
    if isinstance(dependency, str):
        name = dependency
        dependency = get_dependency(dependency, overrides, buildpack_dir)
        if dependency is None:
            logging.error("Cannot find dependency [%s]", name)
            return
    name = _get_dependency_name(dependency)

    logging.debug("Resolving dependency [%s]...", name)
    url = _get_dependency_artifact_url(dependency)
    if url is None:
        logging.error("Cannot find dependency artifact URL for [%s]", name)
        return
    file_name = url.split("/")[-1]

    mkdir_p(cache_dir)
    alias = None
    if DEPENDENCY_ALIAS_KEY in dependency:
        alias = dependency[DEPENDENCY_ALIAS_KEY]

    if DEPENDENCY_VERSION_KEY in dependency:
        _delete_other_versions(cache_dir, file_name, alias)

    vendor_dir = os.path.join(buildpack_dir, "vendor")
    logging.debug(
        "Looking for [%s] in [%s] and [%s]...", file_name, vendor_dir, cache_dir
    )

    vendored_location = _find_file_in_directory(file_name, vendor_dir)
    cached_location = os.path.join(cache_dir, file_name)
    CACHED_DEPENDENCIES.append(cached_location)
    if not is_path_accessible(vendored_location):
        if ignore_cache or not is_path_accessible(cached_location):
            download(url, cached_location)
        else:
            logging.debug(
                "Found dependency in cache, not downloading [%s]", cached_location
            )
    else:
        shutil.copy(vendored_location, cached_location)
        logging.debug(
            "Found vendored dependency, not downloading [%s]", vendored_location
        )
    if destination:
        mkdir_p(destination)
        if unpack:
            # Unpack the artifact
            logging.debug("Extracting [%s] to [%s]...", cached_location, destination)
            if (
                file_name.endswith(".tar.gz")
                or file_name.endswith(".tgz")
                or file_name.endswith(".tar")
            ):
                unpack_cmd = ["tar", "xf", cached_location, "-C", destination]
                if unpack_strip_directories:
                    unpack_cmd.extend(("--strip", "1"))
            else:
                unpack_cmd = [
                    "unzip",
                    "-q",
                    cached_location,
                    "-d",
                    destination,
                ]

            if unpack_cmd:
                subprocess.check_call(unpack_cmd)

        else:
            # Copy the artifact, don't unpack
            logging.debug("Copying [%s] to [%s]...", cached_location, destination)
            shutil.copy(cached_location, os.path.join(destination, file_name))

        logging.debug("Dependency [%s] is now present at [%s]", file_name, destination)
    return dependency


def mkdir_p(path):
    os.makedirs(path, exist_ok=True)


def get_buildpack_loglevel():
    if os.getenv("BUILDPACK_XTRACE", "false") == "true":
        return logging.DEBUG
    return logging.INFO


def download(url, destination):
    logging.debug("Downloading [%s] to [%s]...", url, destination)
    with open(destination, "wb") as file_handle:
        response = requests.get(url, stream=True)
        if not response.ok:
            response.raise_for_status()
        for block in response.iter_content(4096):
            if not block:
                break
            file_handle.write(block)


def get_existing_directory_or_raise(dirs, error):
    for directory in dirs:
        if os.path.isdir(directory):
            return directory
    raise NotFoundException(error)


class NotFoundException(Exception):
    pass


def get_mpr_file_from_dir(directory):
    mprs = [x for x in os.listdir(directory) if x.endswith(".mpr")]
    if len(mprs) == 1:
        return os.path.join(directory, mprs[0])
    if len(mprs) > 1:
        raise Exception("More than one .mpr file found, can not continue")
    return None


def set_up_launch_environment(deps_dir, profile_dir):
    profile_dirs = get_existing_deps_dirs(deps_dir, "profile.d", deps_dir)
    for directory in profile_dirs:
        sections = directory.split(os.sep)
        if len(sections) < 2:
            raise Exception("Invalid dependencies directory")

        deps_idx = sections[len(sections) - 2]

        files = [
            f
            for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f))  # noqa: C0301
        ]

        for f in files:
            src = os.path.join(directory, f)
            dest = os.path.join(profile_dir, deps_idx + "_" + f)
            shutil.copyfile(src, dest)


def get_existing_deps_dirs(deps_dir, sub_dir, prefix):
    files = [
        f for f in os.listdir(deps_dir) if os.path.isdir(os.path.join(deps_dir, f))
    ]
    existing_dirs = []

    for f in files:
        filesystem_dir = os.path.join(deps_dir, f, sub_dir)
        dir_to_join = os.path.join(prefix, f, sub_dir)

        if os.path.exists(filesystem_dir):
            existing_dirs.append(dir_to_join)

    return existing_dirs


def lazy_remove_file(filename):
    try:
        os.remove(filename)
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            raise


# The Mendix runtime knows the concept of "cluster leader" and "cluster member"
# The first instance in a Cloud Foundry deployment is always the cluster leader
def is_cluster_leader():
    return os.getenv("CF_INSTANCE_INDEX", "0") == "0"


def is_free_app():
    return os.getenv("PROFILE") == "free"


def get_nginx_port():
    return int(os.environ["PORT"])


def get_runtime_port():
    return get_nginx_port() + 1


def get_admin_port():
    return get_nginx_port() + 2


def is_development_mode():
    return os.getenv("DEVELOPMENT_MODE", "").lower() == "true"


def get_current_buildpack_commit():
    try:
        with open(".commit", "r") as commit_file:
            short_commit = commit_file.readline().strip()
            return short_commit
    except OSError:
        return "HEAD"


def get_buildpack_version():
    try:
        with open("VERSION", "r") as version_file:
            return version_file.readline().strip()
    except OSError:
        return "DEVELOPMENT"


def get_tags():
    # Tags are strings in a JSON array and must be in key:value format
    tags = []
    try:
        tags = json.loads(os.getenv("TAGS", "[]"))
    except ValueError:
        logging.warning("Invalid TAGS set. Please check if it is a valid JSON array.")

    result = {}
    for kv in [t.split(":") for t in tags]:
        if len(kv) == 2:
            result[kv[0]] = kv[1]
        else:
            logging.warning(
                "Skipping tag [%s] from TAGS: not in key:value format", kv[0]
            )
    return result


def is_url(url):
    try:
        result = urllib.parse.urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def is_path_accessible(path, mode=os.R_OK):
    return path and os.path.exists(path) and os.access(os.path.dirname(path), mode)


def set_executable(path_or_glob):
    if is_path_accessible(path_or_glob, mode=os.W_OK):
        files = [path_or_glob]
    else:
        files = glob.glob(path_or_glob)
    for f in files:
        if not os.access(f, os.X_OK):
            logging.debug("Setting executable permissions for [%s]...", f)
            try:
                os.chmod(
                    f,
                    os.stat(f).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
                )
            except PermissionError as err:
                logging.exception(
                    "Cannot set executable permissions for [%s]: %s", f, err
                )
        else:
            logging.debug("[%s] is already executable, skipping", f)


# m2ee-tools utility functions for manipulating m2ee-tools and runtime configuration

M2EE_TOOLS_CUSTOM_RUNTIME_SETTINGS_SECTION = "mxruntime"
M2EE_MICROFLOW_CONSTANTS_KEY = "MicroflowConstants"
M2EE_TOOLS_SETTINGS_SECTION = "m2ee"
M2EE_TOOLS_JAVAOPTS_KEY = "javaopts"
M2EE_TOOLS_CUSTOM_ENV_KEY = "custom_environment"


# Returns if a value is a sequence or mapping
def _is_sequence_or_mapping(value):
    if isinstance(value, str):
        return False
    return isinstance(value, collections.abc.Sequence) or isinstance(
        value, collections.abc.Mapping
    )


# Upserts a key-value pair into a configuration
# A number of variations of "append" and "overwrite" can be set
# Depending on the value type, this has different outcomes
def _upsert_config(config, key, value, overwrite=False, append=False):
    if key in config:
        if not append and overwrite:
            config[key] = value
        else:
            if append and type(config[key]) == type(value):
                if isinstance(value, list):
                    config[key].extend(value)
                elif isinstance(value, (dict, set)):
                    if overwrite:
                        # New config value = old config value + value
                        config[key].update(value)
                    else:
                        # New config value = value + old config value
                        value.update(config[key])
                        config[key] = value
                else:
                    config[key] += value
            else:
                raise ValueError("Cannot overwrite or append configuration")
    else:
        config[key] = value


# Upserts a key-value pair into a section of the m2ee-tools config
# Operation: config[section][key] (+)= value
def _upsert_m2ee_config_setting(
    m2ee, section, key, value, overwrite=False, append=False
):
    _upsert_config(
        m2ee.config._conf[section],
        key,
        value,
        append=append,
        overwrite=overwrite,
    )


# Upserts a complete section into the m2ee-tools config
# Operation: config[section] (+)= settings
def _upsert_m2ee_config_section(m2ee, section, settings, overwrite=False, append=False):
    _upsert_config(
        m2ee.config._conf,
        section,
        settings,
        append=append,
        overwrite=overwrite,
    )


# Upserts a custom runtime setting
# Operation: config["mxruntime"][key] (+)= value
def upsert_custom_runtime_setting(m2ee, key, value, overwrite=False, append=False):
    _upsert_m2ee_config_setting(
        m2ee,
        M2EE_TOOLS_CUSTOM_RUNTIME_SETTINGS_SECTION,
        key,
        value,
        overwrite,
        append,
    )


# Upserts multiple custom runtime settings
# Operation: config["mxruntime"] (+)= settings
def upsert_custom_runtime_settings(m2ee, settings, overwrite=False, append=False):
    _upsert_m2ee_config_section(
        m2ee,
        M2EE_TOOLS_CUSTOM_RUNTIME_SETTINGS_SECTION,
        settings,
        overwrite,
        append,
    )


# Returns all custom runtime settings
def get_custom_runtime_settings(m2ee):
    return m2ee.config._conf[M2EE_TOOLS_CUSTOM_RUNTIME_SETTINGS_SECTION]


# Returns a single custom runtime setting
def get_custom_runtime_setting(m2ee, key):
    return get_custom_runtime_settings(m2ee)[key]


# Upserts multiple microflow constants
# Operation: config["mxruntime"]["MicroflowConstants"] += value
def upsert_microflow_constants(m2ee, value):
    if not isinstance(value, dict):
        raise ValueError("Value must be a dictionary")
    upsert_custom_runtime_setting(
        m2ee, M2EE_MICROFLOW_CONSTANTS_KEY, value, overwrite=True, append=True
    )


# Returns all microflow constants
def get_microflow_constants(m2ee):
    return get_custom_runtime_setting(m2ee, M2EE_MICROFLOW_CONSTANTS_KEY)


# Upserts an m2ee-tools setting
# Operation: config["m2ee"][key] += value
def upsert_m2ee_tools_setting(m2ee, key, value, overwrite=False, append=False):
    _upsert_m2ee_config_setting(
        m2ee, M2EE_TOOLS_SETTINGS_SECTION, key, value, overwrite, append
    )


# Gets an m2ee-tools setting
# Operation: config["m2ee"][key] += value
def get_m2ee_tools_setting(m2ee, key):
    return m2ee.config._conf[M2EE_TOOLS_SETTINGS_SECTION][key]


# Upserts an m2ee-tools javaopts value
# Operation: config["m2ee"]["javaopts"] += [ value ]
def upsert_javaopts(m2ee, value):
    if not _is_sequence_or_mapping(value):
        value = [value]
    upsert_m2ee_tools_setting(
        m2ee, M2EE_TOOLS_JAVAOPTS_KEY, value, overwrite=False, append=True
    )


# Returns all m2ee-tools javaopts values
def get_javaopts(m2ee):
    return get_m2ee_tools_setting(m2ee, M2EE_TOOLS_JAVAOPTS_KEY)


# Upserts an m2ee-tools custom environment variable
# Operation: config["m2ee"]["custom_environment"][key] = value
def upsert_custom_environment_variable(m2ee, key, value):
    _upsert_config(
        get_custom_environment_variables(m2ee),
        key,
        value,
        overwrite=True,
        append=False,
    )


# Returns all m2ee-tools custom environment variables
def get_custom_environment_variables(m2ee):
    return get_m2ee_tools_setting(m2ee, M2EE_TOOLS_CUSTOM_ENV_KEY)


# Upserts m2ee-tools logging configuration
# Operation: config["logging"] += [ value ]
def upsert_logging_config(m2ee, value):
    if not isinstance(value, dict):
        raise ValueError("Value must be a dictionary")
    _upsert_m2ee_config_section(m2ee, "logging", [value], overwrite=False, append=True)


# Script entry point. Only meant to be used in development
if __name__ == "__main__":
    import sys
    import click

    # Hacks to find project root and make script runnable in most cases
    PROJECT_ROOT_PATH = None
    if "__file__" in vars():
        PROJECT_ROOT_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    else:
        PROJECT_ROOT_PATH = os.getcwd()
    sys.path.append(PROJECT_ROOT_PATH)

    @click.group()
    @click.option(
        "-v",
        "--verbose",
        is_flag=True,
        default=False,
        help="Enables verbose output.",
    )
    @click.pass_context
    def cli(ctx, verbose):
        ctx.obj = {"verbose": verbose}

    @cli.command(help="Lists managed external dependencies")
    @click.pass_context
    def list_external_dependencies(ctx):
        ctx.obj["verbose"]
        for key in _get_dependencies(PROJECT_ROOT_PATH).keys():
            dependency = get_dependency(key)
            if DEPENDENCY_MANAGED_KEY not in dependency or (
                DEPENDENCY_MANAGED_KEY in dependency
                and dependency[DEPENDENCY_MANAGED_KEY] is True
            ):
                click.echo(_get_dependency_artifact_url(dependency))

    # CycloneDX specifications can be found at https://cyclonedx.org/
    @cli.command(
        help="Generate CycloneDX 1.4 Software BOM for managed external dependencies"
    )
    @click.pass_context
    def generate_software_bom(ctx):
        import uuid

        ctx.obj["verbose"]
        # CycloneDX top fields
        result = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.4",
            "serialNumber": f"urn:uuid:{uuid.uuid1()}",
            "version": 1,
        }
        components = []
        for key in _get_dependencies(PROJECT_ROOT_PATH).keys():
            dependency = get_dependency(key)
            if DEPENDENCY_MANAGED_KEY not in dependency or (
                DEPENDENCY_MANAGED_KEY in dependency
                and dependency[DEPENDENCY_MANAGED_KEY] is True
            ):
                # Standard fields
                component = {
                    "type": "library",
                    "name": key,
                    "version": dependency["version"],
                    "url": _get_dependency_artifact_url(dependency),
                }
                # Publisher field
                if "vendor" in dependency:
                    component = {
                        **component,
                        **{"publisher": dependency["vendor"]},
                    }
                # Identifier (CPE, PURL) fields
                for identifier in ["cpe", "purl"]:
                    if identifier in dependency:
                        component = {
                            **component,
                            **{
                                identifier: _render(
                                    dependency, dependency, [identifier]
                                )[identifier]
                            },
                        }
                # BOM prefixed fields
                for bom_key in [x for x in dependency.keys() if x.startswith("bom_")]:
                    real_key = bom_key.split("_")[1]
                    component = {
                        **component,
                        **{
                            real_key: _render(dependency, dependency, [bom_key])[
                                bom_key
                            ]
                        },
                    }
                components.append(component)
        result = {**result, **{"components": components}}
        click.echo(json.dumps(result, indent=4))

    cli()  # pylint: disable=no-value-for-parameter
