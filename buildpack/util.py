import errno
import glob
import json
import logging
import os
import re
import shutil
import subprocess
from distutils.util import strtobool

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


def get_hostname():
    return get_domain() + "-" + os.getenv("CF_INSTANCE_INDEX", "")


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


def download_and_unpack(
    url, destination, cache_dir="/tmp/downloads", unpack=True, alias=None
):
    file_name = url.split("/")[-1]
    mkdir_p(cache_dir)
    cached_location = os.path.join(cache_dir, file_name)

    _delete_other_versions(cache_dir, file_name, alias)

    logging.debug(
        "Looking for [{cached_location}] in cache...".format(
            cached_location=cached_location
        )
    )

    if not os.path.isfile(cached_location):
        download(url, cached_location)
    else:
        logging.debug(
            "Found in cache, not downloading [{cached_location}]".format(
                cached_location=cached_location
            )
        )
    if destination:
        mkdir_p(destination)
        if unpack:
            # Unpack the artifact
            logging.debug(
                "Extracting [{cached_location}] to [{dest}]...".format(
                    cached_location=cached_location, dest=destination
                )
            )
            if (
                file_name.endswith(".tar.gz")
                or file_name.endswith(".tgz")
                or file_name.endswith(".tar")
            ):
                unpack_cmd = ["tar", "xf", cached_location, "-C", destination]
                if file_name.startswith(
                    ("mono-", "jdk-", "jre-", "AdoptOpenJDK-")
                ):
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
                "Copying [{cached_location}] to [{dest}]...".format(
                    cached_location=cached_location, dest=destination
                )
            )
            shutil.copyfile(
                cached_location, os.path.join(destination, file_name)
            )

        logging.debug(
            "Dependency [{file_name}] is now present at [{destination}]".format(
                file_name=file_name, destination=destination,
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


def i_am_primary_instance():
    return os.getenv("CF_INSTANCE_INDEX", "0") == "0"


def is_free_app():
    return os.getenv("PROFILE") == "free"


def get_nginx_port():
    return int(os.environ["PORT"])


def get_runtime_port():
    return get_nginx_port() + 1


def get_admin_port():
    return get_nginx_port() + 2


def get_deploy_port():
    return get_nginx_port() + 3


def bypass_loggregator():
    env_var = os.getenv("BYPASS_LOGGREGATOR", "False")
    # Throws a useful message if you put in a nonsensical value.
    # Necessary since we store these in cloud portal as strings.
    try:
        bypass = strtobool(env_var)
    except ValueError as _:
        logging.warning(
            "Bypass loggregator has a nonsensical value: %s. "
            "Falling back to old loggregator-based metric reporting.",
            env_var,
        )
        return False

    if bypass:
        if os.getenv("TRENDS_STORAGE_URL"):
            return True
        else:
            logging.warning(
                "BYPASS_LOGGREGATOR is set to true, but no metrics URL is "
                "set. Falling back to old loggregator-based metric reporting."
            )
            return False
    return False


def is_development_mode():
    return os.getenv("DEVELOPMENT_MODE", "").lower() == "true"


def get_current_buildpack_commit():
    try:
        with open(".commit", "r") as commit_file:
            short_commit = commit_file.readline().strip()
            return short_commit
    except OSError:
        return "unknown_commit"


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
