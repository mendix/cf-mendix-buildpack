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


def print_all_logging_handlers():
    for k, v in logging.Logger.manager.loggerDict.items():
        print("+ [%s] {%s} " % (str.ljust(k, 20), str(v.__class__)[8:-2]))
        if not isinstance(v, logging.PlaceHolder):
            for h in v.handlers:
                print("     +++", str(h.__class__)[8:-2])


def get_vcap_services_data():
    if os.environ.get("VCAP_SERVICES"):
        return json.loads(os.environ.get("VCAP_SERVICES"))
    else:
        return {}


def get_vcap_data():
    if os.environ.get("VCAP_APPLICATION"):
        return json.loads(os.environ.get("VCAP_APPLICATION"))
    else:
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
        result += "-{}".format(cf_instance_index)
    return result


def get_app_from_domain():
    return get_domain().split(".")[0]


def get_blobstore():
    return os.environ.get("BLOBSTORE", "https://cdn.mendix.com")


def get_blobstore_url(filename, blobstore=get_blobstore()):
    main_url = blobstore
    if main_url[-1] == "/":
        main_url = main_url[0:-1]
    return main_url + filename


def _delete_other_versions(directory, file_name, alias=None):
    logging.debug(
        "Deleting other dependency versions than [{}] from [{}]...".format(
            file_name, directory
        )
    )
    expression = r"^((?:[a-zA-Z]+-)+)((?:v*[0-9]+\.?)+.*)(\.(?:tar|tar\.gz|tgz|zip|jar))$"
    patterns = [re.sub(expression, "\\1*\\3", file_name)]
    if alias:
        patterns.append("{}-*.*".format(alias))

    for pattern in patterns:
        logging.debug("Finding files matching [{}]...".format(pattern))
        files = glob.glob("{}/{}".format(directory, pattern))

        for f in files:
            if os.path.basename(f) != file_name:
                logging.debug(
                    "Deleting version [{}] from [{}]...".format(
                        os.path.basename(f), directory
                    )
                )
                os.remove(f)


def _find_file_in_directory(file_name, directory):
    paths = [
        a
        for a in [
            os.path.abspath(p)
            for p in glob.glob(
                "{}/**/{}".format(directory, file_name), recursive=True
            )
        ]
        if os.path.isfile(a)
    ]

    if len(paths) > 0:
        return paths[0]
    return None


def resolve_dependency(
    url,
    destination,
    buildpack_dir,
    cache_dir="/tmp/downloads",
    ignore_cache=False,
    unpack=True,
    unpack_strip_directories=False,
    alias=None,
):
    file_name = url.split("/")[-1]

    mkdir_p(cache_dir)
    _delete_other_versions(cache_dir, file_name, alias)

    vendor_dir = os.path.join(buildpack_dir, "vendor")
    logging.debug(
        "Looking for [{}] in [{}] and [{}]...".format(
            file_name, vendor_dir, cache_dir
        )
    )

    vendored_location = _find_file_in_directory(file_name, vendor_dir)
    cached_location = os.path.join(cache_dir, file_name)
    if not is_path_accessible(vendored_location):
        if ignore_cache or not is_path_accessible(cached_location):
            download(url, cached_location)
        else:
            logging.debug(
                "Found dependency in cache, not downloading [{}]".format(
                    cached_location
                )
            )
    else:
        shutil.copy(vendored_location, cached_location)
        logging.debug(
            "Found vendored dependency, not downloading [{}]".format(
                vendored_location
            )
        )
    if destination:
        mkdir_p(destination)
        if unpack:
            # Unpack the artifact
            logging.debug(
                "Extracting [{}] to [{}]...".format(
                    cached_location, destination
                )
            )
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
            logging.debug(
                "Copying [{}] to [{}]...".format(cached_location, destination)
            )
            shutil.copy(cached_location, os.path.join(destination, file_name))

        logging.debug(
            "Dependency [{}] is now present at [{}]".format(
                file_name, destination
            )
        )


def mkdir_p(path):
    os.makedirs(path, exist_ok=True)


def get_buildpack_loglevel():
    if os.getenv("BUILDPACK_XTRACE", "false") == "true":
        return logging.DEBUG
    return logging.INFO


def download(url, destination):
    logging.debug(
        "Downloading [{url}] to [{destination}]...".format(
            url=url, destination=destination
        )
    )
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
    elif len(mprs) > 1:
        raise Exception("More than one .mpr file found, can not continue")
    else:
        return None


def lazy_remove_file(filename):
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
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
        return "development"


def get_buildpack_version():
    try:
        with open("VERSION", "r") as version_file:
            return version_file.readline().strip()
    except OSError:
        return "unversioned"


def get_tags():
    # Tags are strings in a JSON array and must be in key:value format
    tags = []
    try:
        tags = json.loads(os.getenv("TAGS", "[]"))
    except ValueError:
        logging.warning(
            "Invalid TAGS set. Please check if it is a valid JSON array."
        )

    result = {}
    for kv in [t.split(":") for t in tags]:
        if len(kv) == 2:
            result[kv[0]] = kv[1]
        else:
            logging.warning(
                "Skipping tag [{}] from TAGS: not in key:value format".format(
                    kv[0]
                )
            )
    return result


def is_url(url):
    try:
        result = urllib.parse.urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def is_path_accessible(path, mode=os.R_OK):
    return (
        path
        and os.path.exists(path)
        and os.access(os.path.dirname(path), mode)
    )


def set_executable(path_or_glob):
    if is_path_accessible(path_or_glob, mode=os.W_OK):
        files = [path_or_glob]
    else:
        files = glob.glob(path_or_glob)
    for f in files:
        if not os.access(f, os.X_OK):
            logging.debug(
                "Setting executable permissions for [{}]...".format(f)
            )
            try:
                os.chmod(
                    f,
                    os.stat(f).st_mode
                    | stat.S_IXUSR
                    | stat.S_IXGRP
                    | stat.S_IXOTH,
                )
            except PermissionError as err:
                logging.exception(
                    "Cannot set executable permissions for [{}]".format(f), err
                )
        else:
            logging.debug("[{}] is already executable, skipping".format(f))


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
    return isinstance(value, collections.Sequence) or isinstance(
        value, collections.Mapping
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
                elif isinstance(value, set) or isinstance(value, dict):
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
def _upsert_m2ee_config_section(
    m2ee, section, settings, overwrite=False, append=False
):
    _upsert_config(
        m2ee.config._conf,
        section,
        settings,
        append=append,
        overwrite=overwrite,
    )


# Upserts a custom runtime setting
# Operation: config["mxruntime"][key] (+)= value
def upsert_custom_runtime_setting(
    m2ee, key, value, overwrite=False, append=False
):
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
def upsert_custom_runtime_settings(
    m2ee, settings, overwrite=False, append=False
):
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
    _upsert_m2ee_config_section(
        m2ee, "logging", [value], overwrite=False, append=True
    )
