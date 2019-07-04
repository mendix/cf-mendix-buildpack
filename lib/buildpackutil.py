import errno
import json
import logging
import os
import subprocess
import sys
from distutils.util import strtobool

sys.path.insert(0, "lib")

import requests  # noqa: E402

from m2ee.version import MXVersion  # noqa: E402


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


def appdynamics_used():
    for k, v in os.environ.items():
        if k.startswith("APPDYNAMICS_"):
            return True
    return False


def get_new_relic_license_key():
    vcap_services = get_vcap_services_data()
    if vcap_services and "newrelic" in vcap_services:
        return vcap_services["newrelic"][0]["credentials"]["licenseKey"]
    return None


def is_appmetrics_enabled():
    return os.getenv("APPMETRICS_TARGET") is not None


def get_tags():
    return json.loads(os.getenv("TAGS", os.getenv("DD_TAGS", "[]")))


def get_hostname():
    dd_hostname = os.environ.get("DD_HOSTNAME")
    if dd_hostname is None:
        domain = get_vcap_data()["application_uris"][0].split("/")[0]
        dd_hostname = domain + "-" + os.getenv("CF_INSTANCE_INDEX", "")
    return dd_hostname


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
    else:
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


def get_java_version(mx_version):
    if mx_version >= MXVersion("8.0.0"):
        java_version = {
            "version": os.getenv("JAVA_VERSION", "11.0.3"),
            "vendor": "AdoptOpenJDK",
        }
    elif mx_version >= MXVersion("7.23.1"):
        java_version = {
            "version": os.getenv("JAVA_VERSION", "8u202"),
            "vendor": "AdoptOpenJDK",
        }
    elif mx_version >= MXVersion("6.6"):
        java_version = {
            "version": os.getenv("JAVA_VERSION", "8u202"),
            "vendor": "oracle",
        }
    elif mx_version >= MXVersion("5.18"):
        java_version = {
            "version": os.getenv("JAVA_VERSION", "8u51"),
            "vendor": "oracle",
        }
    else:
        java_version = {
            "version": os.getenv("JAVA_VERSION", "7u80"),
            "vendor": "oracle",
        }

    return java_version


def get_mpr_file_from_dir(directory):
    mprs = [x for x in os.listdir(directory) if x.endswith(".mpr")]
    if len(mprs) == 1:
        return os.path.join(directory, mprs[0])
    elif len(mprs) > 1:
        raise Exception("More than one .mpr file found, can not continue")
    else:
        return None


def ensure_mxbuild_in_directory(directory, mx_version, cache_dir):
    if os.path.isdir(os.path.join(directory, "modeler")):
        return
    mkdir_p(directory)

    url = os.environ.get("FORCED_MXBUILD_URL")
    if url:
        # don"t ever cache with a FORCED_MXBUILD_URL
        download_and_unpack(url, directory, cache_dir="/tmp/downloads")
    else:
        try:
            _checkout_from_git_rootfs(directory, mx_version)
        except NotFoundException as e:
            logging.debug(str(e))
            download_and_unpack(
                get_blobstore_url(
                    "/runtime/mxbuild-%s.tar.gz" % str(mx_version)
                ),
                directory,
                cache_dir=cache_dir,
            )


def _checkout_from_git_rootfs(directory, mx_version):
    mendix_runtimes_path = "/usr/local/share/mendix-runtimes.git"
    if not os.path.isdir(mendix_runtimes_path):
        raise NotFoundException()

    env = dict(os.environ)
    env["GIT_WORK_TREE"] = directory

    # checkout the runtime version
    try:
        subprocess.check_call(
            ("git", "checkout", str(mx_version), "-f"),
            cwd=mendix_runtimes_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return
    except Exception:
        try:
            subprocess.check_call(
                (
                    "git",
                    "fetch",
                    "origin",
                    "refs/tags/{0}:refs/tags/{0}".format(str(mx_version)),
                ),
                cwd=mendix_runtimes_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.check_call(
                ("git", "checkout", str(mx_version), "-f"),
                cwd=mendix_runtimes_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logging.debug("found mx version after updating runtimes.git")
            return
        except Exception:
            logging.debug("tried updating git repo, also failed")
    raise NotFoundException(
        "Could not download mxbuild "
        + str(mx_version)
        + " from updated git repo"
    )


def _get_env_with_monolib(mono_dir):
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = mono_dir + "/lib"
    env["MONO_STRICT_MS_COMPLIANT"] = "yes"
    if not os.path.isfile(os.path.join(mono_dir, "lib", "libgdiplus.so")):
        raise Exception("libgdiplus.so not found in dir %s" % mono_dir)
    return env


def _detect_mono_version(mx_version):
    logging.debug(
        "Detecting Mono Runtime using mendix version: " + str(mx_version)
    )

    if mx_version >= 8:
        target = "mono-5.20.1.27"
    elif mx_version >= 7:
        target = "mono-4.6.2.16"
    else:
        target = "mono-3.10.0"
    logging.info("Selecting Mono Runtime: " + target)
    return target


def _get_mono_path(directory, mono_version):
    return get_existing_directory_or_raise(
        [
            os.path.join(directory, mono_version),
            "/opt/" + mono_version,
            "/tmp/" + mono_version,
        ],
        "Mono not found",
    )


def lazy_remove_file(filename):
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def ensure_and_get_mono(mx_version, cache_dir):
    logging.debug(
        "ensuring mono for mendix {mx_version}".format(
            mx_version=str(mx_version)
        )
    )
    mono_version = _detect_mono_version(mx_version)
    fallback_location = "/tmp/opt"
    try:
        mono_location = _get_mono_path("/tmp/opt", mono_version)
    except NotFoundException:
        logging.debug("Mono not found in default locations")
        download_and_unpack(
            get_blobstore_url("/mx-buildpack/" + mono_version + "-mx.tar.gz"),
            os.path.join(fallback_location, mono_version),
            cache_dir,
        )
        mono_location = _get_mono_path(fallback_location, mono_version)
    logging.debug("Using {mono_location}".format(mono_location=mono_location))
    return mono_location


def _determine_jdk(mx_version, package="jdk"):
    java_version = get_java_version(mx_version)

    if java_version["vendor"] == "AdoptOpenJDK":
        java_version.update({"type": "AdoptOpenJDK-{}".format(package)})
    else:
        java_version.update({"type": package})

    return java_version


def _compose_jvm_target_dir(jdk):
    return "usr/lib/jvm/{type}-{version}-{vendor}-x64".format(
        type=jdk["type"], version=jdk["version"], vendor=jdk["vendor"]
    )


def _compose_jre_url_path(jdk):
    return "/mx-buildpack/{type}-{version}-linux-x64.tar.gz".format(
        type=jdk["type"], version=jdk["version"]
    )


def ensure_and_get_jvm(
    mx_version, cache_dir, dot_local_location, package="jdk"
):
    logging.debug("Begin download and install java %s" % package)

    jdk = _determine_jdk(mx_version, package)

    rootfs_java_path = "/{}".format(_compose_jvm_target_dir(jdk))
    if not os.path.isdir(rootfs_java_path):
        logging.debug("rootfs without java sdk detected")
        download_and_unpack(
            get_blobstore_url(_compose_jre_url_path(jdk)),
            os.path.join(dot_local_location, _compose_jvm_target_dir(jdk)),
            cache_dir,
        )
    else:
        logging.debug("rootfs with java sdk detected")
    logging.debug("end download and install java %s" % package)

    return get_existing_directory_or_raise(
        [
            "/" + _compose_jvm_target_dir(jdk),
            os.path.join(dot_local_location, _compose_jvm_target_dir(jdk)),
        ],
        "Java not found",
    )


def update_java_cacert(buildpack_dir, jvm_location):
    logging.debug("Applying Mozilla CA certificates update to JVM cacerts...")
    cacerts_file = os.path.join(jvm_location, "lib", "security", "cacerts")
    if not os.path.exists(cacerts_file):
        logging.warning(
            "Cannot locate cacerts file {}. Skippiung update of CA certiticates.".format(
                cacerts_file
            )
        )
        return

    update_cacert_path = os.path.join(buildpack_dir, "lib", "cacert")
    if not os.path.exists(update_cacert_path):
        logging.warning(
            "Cannot locate cacert lib folder {}. Skipping  update of CA certificates.".format(
                update_cacert_path
            )
        )
        return

    cacert_merged = "cacerts.merged"
    env = dict(os.environ)

    try:
        subprocess.check_output(
            (
                os.path.join(jvm_location, "bin", "java"),
                "-jar",
                os.path.join(update_cacert_path, "keyutil-0.4.0.jar"),
                "-i",
                "--new-keystore",
                cacert_merged,
                "--password",
                "changeit",
                "--import-pem-file",
                os.path.join(update_cacert_path, "cacert.pem"),
                "--import-jks-file",
                "{}:changeit".format(cacerts_file),
            ),
            env=env,
            stderr=subprocess.STDOUT,
        )
    except Exception as ex:
        logging.error("Error applying cacert update: {}".format(ex.output), ex)
        raise ex

    os.rename(cacert_merged, cacerts_file)
    logging.debug("Update of cacerts file finished.")


def i_am_primary_instance():
    return os.getenv("CF_INSTANCE_INDEX", "0") == "0"


def bypass_loggregator_logging():
    env_var = os.getenv("BYPASS_LOGGREGATOR", "False")
    # Throws a useful message if you put in a nonsensical value.
    # Necessary since we store these in cloud portal as strings.
    try:
        bypass_loggregator = strtobool(env_var)
    except ValueError as e:
        logging.warning(
            "Bypass loggregator has a nonsensical value: %s. "
            "Falling back to old loggregator-based metric reporting.",
            env_var,
        )
        return False

    if bypass_loggregator:
        if os.getenv("TRENDS_STORAGE_URL"):
            return True
        else:
            logging.warning(
                "BYPASS_LOGGREGATOR is set to true, but no metrics URL is "
                "set. Falling back to old loggregator-based metric reporting."
            )
            return False
    return False


def get_metrics_url():
    return os.getenv("TRENDS_STORAGE_URL")
