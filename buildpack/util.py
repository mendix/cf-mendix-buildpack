import errno
import json
import logging
import os
import subprocess
import sys
from distutils.util import strtobool

import requests

sys.path.insert(0, "lib")


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
            "application_uris": ["example.com"],
            "application_name": "My App",
        }


def is_appmetrics_enabled():
    return os.getenv("APPMETRICS_TARGET") is not None


def get_tags():
    return json.loads(os.getenv("TAGS", os.getenv("DD_TAGS", "[]")))


def get_domain():
    return get_vcap_data()["application_uris"][0].split("/")[0]


def get_hostname():
    dd_hostname = os.environ.get("DD_HOSTNAME")
    if dd_hostname is None:
        dd_hostname = get_domain() + "-" + os.getenv("CF_INSTANCE_INDEX", "")
    return dd_hostname


def get_appname():
    return "".join(
        filter(lambda x: not x.isdigit(), get_domain().split("-")[0])
    )


def get_blobstore_url(filename):
    main_url = os.environ.get("BLOBSTORE", "https://cdn.mendix.com")
    if main_url[-1] == "/":
        main_url = main_url[0:-1]
    return main_url + filename


def download_and_unpack(url, destination, cache_dir="/tmp/downloads"):
    file_name = url.split("/")[-1]
    mkdir_p(cache_dir)
    mkdir_p(destination)
    cached_location = os.path.join(cache_dir, file_name)

    logging.debug(
        "Looking for {cached_location}".format(cached_location=cached_location)
    )

    if not os.path.isfile(cached_location):
        download(url, cached_location)
        logging.debug(
            "downloaded to {cached_location}".format(
                cached_location=cached_location
            )
        )
    else:
        logging.debug(
            "found in cache: {cached_location}".format(
                cached_location=cached_location
            )
        )

    logging.debug(
        "extracting: {cached_location} to {dest}".format(
            cached_location=cached_location, dest=destination
        )
    )
    if file_name.endswith(".tar.gz") or file_name.endswith(".tgz"):
        unpack_cmd = ["tar", "xf", cached_location, "-C", destination]
        if file_name.startswith(("mono-", "jdk-", "jre-", "AdoptOpenJDK-")):
            unpack_cmd.extend(("--strip", "1"))
        subprocess.check_call(unpack_cmd)
    else:
        raise Exception(
            "do not know how to unpack {cached_location}".format(
                cached_location=cached_location
            )
        )

    logging.debug(
        "source {file_name} retrieved & unpacked in {destination}".format(
            file_name=file_name, destination=destination
        )
    )


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def get_buildpack_loglevel():
    if os.getenv("BUILDPACK_XTRACE", "false") == "true":
        return logging.DEBUG
    return logging.INFO


def download(url, destination):
    logging.debug(
        "downloading {url} to {destination}".format(
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


def use_instadeploy(mx_version):
    return mx_version >= 6.7


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
        with open(".buildpack_commit", "r") as commit_file:
            short_commit = commit_file.readline().strip()
            return short_commit
    except OSError:
        return "unknown_commit"
