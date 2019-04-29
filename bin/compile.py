#!/usr/bin/env python3
import codecs
import json
import logging
import os
import shutil
import subprocess
import sys

import requests
import zipfile

import datadog
import database_config
import telegraf
import buildpackutil
from m2ee.version import MXVersion

BUILDPACK_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
BUILD_DIR = sys.argv[1]
CACHE_DIR = os.path.join(sys.argv[2], "bust")
DOT_LOCAL_LOCATION = os.path.join(BUILD_DIR, ".local")
BUILD_ERRORS_JSON = "/tmp/builderrors.json"


logging.basicConfig(
    level=buildpackutil.get_buildpack_loglevel(),
    stream=sys.stdout,
    format="%(levelname)s: %(message)s",
)

logging.getLogger("requests").setLevel(logging.WARNING)


def get_runtime_version():
    file_name = os.path.join(BUILD_DIR, "model", "metadata.json")
    try:
        with open(file_name) as file_handle:
            data = json.loads(file_handle.read())
            return MXVersion(data["RuntimeVersion"])
    except IOError:
        mpr = get_mpr_file()
        if not mpr:
            raise Exception("No model/metadata.json or .mpr found in archive")
        import sqlite3

        cursor = sqlite3.connect(mpr).cursor()
        cursor.execute("SELECT _ProductVersion FROM _MetaData LIMIT 1")
        record = cursor.fetchone()
        return MXVersion(record[0])


def check_environment_variable(variable, explanation):
    value = os.environ.get(variable)
    if value is None:
        logging.warning(explanation)
        return False
    else:
        return True


def get_current_git_commit():
    try:
        raw_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=BUILDPACK_DIR
        )
        commit = raw_commit.decode("utf-8").strip()
        short_commit = commit[:7]
        return short_commit
    except Exception:
        logging.warning(
            "MENDIX BUILDPACK: Unable to determine exact version "
            "in use. This is nothing to worry about",
            exc_info=True,
        )
        return "unknown_commit"


def write_current_git_commit():
    short_commit = get_current_git_commit()
    with open(
        os.path.join(BUILD_DIR, ".buildpack_commit"), "w"
    ) as version_file:
        logging.debug("Building with commit %s", short_commit)
        version_file.write(short_commit)


def set_up_appdynamics():
    if buildpackutil.appdynamics_used():
        buildpackutil.download_and_unpack(
            buildpackutil.get_blobstore_url(
                "/mx-buildpack/appdynamics-agent-4.3.5.7.tar.gz"
            ),
            DOT_LOCAL_LOCATION,
            CACHE_DIR,
        )


def check_database_environment_variable():
    try:
        database_config.get_database_config()
        return True
    except Exception as e:
        logging.error(
            "You should provide a DATABASE_URL by adding a database service "
            "to this application, it can be either MySQL or Postgres "
            "If this is the first push of a new app, set up a database service "
            "and push again afterwards: %s",
            e,
        )
        return False


def set_up_java():
    logging.debug("begin download and install java")
    buildpackutil.mkdir_p(os.path.join(DOT_LOCAL_LOCATION, "bin"))
    jvm_location = buildpackutil.ensure_and_get_jvm(
        get_runtime_version(), CACHE_DIR, DOT_LOCAL_LOCATION, package="jre"
    )
    # create a symlink in .local/bin/java
    os.symlink(
        # use .. when jdk is in .local because absolute path is different at staging time
        os.path.join(
            jvm_location.replace(DOT_LOCAL_LOCATION, ".."), "bin", "java"
        ),
        os.path.join(DOT_LOCAL_LOCATION, "bin", "java"),
    )
    # update cacert file
    buildpackutil.update_java_cacert(BUILDPACK_DIR, jvm_location)
    logging.debug("end download and install java")


def preflight_check():
    logging.debug("pre-flight-check")
    if not check_database_environment_variable():
        raise Exception("Missing environment variables")


def set_up_directory_structure():
    logging.debug("making directory structure")
    buildpackutil.mkdir_p(DOT_LOCAL_LOCATION)
    for name in ["runtimes", "log", "database", "data", "bin"]:
        buildpackutil.mkdir_p(os.path.join(BUILD_DIR, name))
    for name in ["files", "tmp"]:
        buildpackutil.mkdir_p(os.path.join(BUILD_DIR, "data", name))


def download_mendix_version():
    logging.debug("downloading mendix version")

    git_repo_found = os.path.isdir("/usr/local/share/mendix-runtimes.git")

    if git_repo_found and not os.environ.get("FORCED_MXRUNTIME_URL"):
        logging.debug("rootfs with mendix runtime detected, skipping download")
        return

    url = os.environ.get("FORCED_MXRUNTIME_URL")
    if url is not None:
        cache_dir = "/tmp/downloads"
    else:
        cache_dir = CACHE_DIR
        url = buildpackutil.get_blobstore_url(
            "/runtime/mendix-%s.tar.gz" % str(get_runtime_version())
        )
    logging.debug(
        "rootfs without mendix runtimes detected, "
        "downloading and unpacking mendix runtime now"
    )
    buildpackutil.download_and_unpack(
        url, os.path.join(BUILD_DIR, "runtimes"), cache_dir=cache_dir
    )


def copy_buildpack_resources():
    shutil.copy(
        os.path.join(BUILDPACK_DIR, "m2ee.yaml"),
        os.path.join(DOT_LOCAL_LOCATION, "m2ee.yaml"),
    )
    shutil.copy(
        os.path.join(BUILDPACK_DIR, "start.py"),
        os.path.join(BUILD_DIR, "start.py"),
    )
    shutil.copytree(
        os.path.join(BUILDPACK_DIR, "nginx"), os.path.join(BUILD_DIR, "nginx")
    )
    shutil.copytree(
        os.path.join(BUILDPACK_DIR, "lib"), os.path.join(BUILD_DIR, "lib")
    )
    shutil.copy(
        os.path.join(BUILDPACK_DIR, "bin", "mendix-logfilter"),
        os.path.join(BUILD_DIR, "bin", "mendix-logfilter"),
    )
    if buildpackutil.get_new_relic_license_key():
        shutil.copytree(
            os.path.join(BUILDPACK_DIR, "newrelic"),
            os.path.join(BUILD_DIR, "newrelic"),
        )


def get_mpr_file():
    return buildpackutil.get_mpr_file_from_dir(BUILD_DIR)


def is_source_push():
    if get_mpr_file() is not None:
        return True
    else:
        return False


def run_mx_build():
    mx_version = get_runtime_version()
    mono_location = buildpackutil.ensure_and_get_mono(mx_version, CACHE_DIR)
    logging.debug(
        "Mono available: {mono_location}".format(mono_location=mono_location)
    )
    mono_env = buildpackutil._get_env_with_monolib(mono_location)

    mxbuild_location = os.path.join(DOT_LOCAL_LOCATION, "mxbuild")

    buildpackutil.ensure_mxbuild_in_directory(
        mxbuild_location, mx_version, CACHE_DIR
    )

    jvm_location = buildpackutil.ensure_and_get_jvm(
        mx_version, CACHE_DIR, DOT_LOCAL_LOCATION
    )

    buildpackutil.lazy_remove_file(BUILD_ERRORS_JSON)

    args = [
        os.path.join(mono_location, "bin/mono"),
        "--config",
        os.path.join(mono_location, "etc/mono/config"),
        os.path.join(mxbuild_location, "modeler/mxbuild.exe"),
        "--target=package",
        "--output=/tmp/model.mda",
        "--java-home=%s" % jvm_location,
        "--java-exe-path=%s" % os.path.join(jvm_location, "bin/java"),
    ]

    if mx_version >= 6.4 or os.environ.get("FORCE_WRITE_BUILD_ERRORS"):
        args.append("--write-errors=%s" % BUILD_ERRORS_JSON)
        logging.debug("Will write build errors to %s" % BUILD_ERRORS_JSON)

    if os.environ.get("FORCED_MXBUILD_URL"):
        args.append("--loose-version-check")
        logging.warning(
            "Using forced mxbuild version, the model will be converted"
        )

    args.append(get_mpr_file())

    try:
        logging.debug("subprocess call {args}".format(args=args))
        subprocess.check_call(args, env=mono_env)
    except subprocess.CalledProcessError as e:
        buildstatus_callback(BUILD_ERRORS_JSON)
        raise e

    for file_name in os.listdir(BUILD_DIR):
        path = os.path.join(BUILD_DIR, file_name)
        if file_name != ".local":
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.unlink(path)

    zf = zipfile.ZipFile("/tmp/model.mda")
    try:
        zf.extractall(BUILD_DIR)
    finally:
        zf.close()

    try:
        with open(os.path.join(BUILD_DIR, ".sourcepush"), "w") as f:
            f.write("sourcepush")
    except Exception as e:
        logging.warning("Could not write source push indicator. %s", str(e))


def buildstatus_callback(error_file):
    generic_build_failure = {
        "problems": [
            {
                "severity": "Error",
                "message": "Failed to build the model, please check application logs for details.",
                "locations": [],
            }
        ]
    }
    input_str = ""
    try:
        with codecs.open(error_file, "r", encoding="utf-8-sig") as b:
            input_str = b.read()
            builddata = json.dumps(json.loads(input_str))
    except (IOError, ValueError):
        logging.exception("Could not read mxbuild error file\n%s" % input_str)
        builddata = json.dumps(generic_build_failure)
    logging.error("MxBuild returned errors: %s" % builddata)
    callback_url = os.environ.get("BUILD_STATUS_CALLBACK_URL")
    if callback_url:
        logging.info("Submitting build status")
        requests.put(callback_url, builddata)
        logging.info("Submitted build status")
    else:
        logging.warning(
            "No build status callback url set, so not going to submit the status"
        )


def set_up_nginx():
    buildpackutil.download_and_unpack(
        buildpackutil.get_blobstore_url(
            "/mx-buildpack/nginx-1.15.10-linux-x64-cflinuxfs2-6247377a.tgz"
        ),
        BUILD_DIR,
        cache_dir=CACHE_DIR,
    )


if __name__ == "__main__":
    preflight_check()
    if is_source_push():
        logging.info("source push detected")
        run_mx_build()
        for folder in ("mxbuild", "mono"):
            path = os.path.join(DOT_LOCAL_LOCATION, folder)
            shutil.rmtree(path, ignore_errors=True)
    set_up_directory_structure()
    set_up_java()
    set_up_appdynamics()
    telegraf.compile(DOT_LOCAL_LOCATION, CACHE_DIR)
    datadog.compile(DOT_LOCAL_LOCATION, CACHE_DIR)
    download_mendix_version()
    copy_buildpack_resources()
    write_current_git_commit()
    set_up_nginx()
    logging.info("buildpack compile completed")
