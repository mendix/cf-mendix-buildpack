#!/usr/bin/env python3
import logging
import os
import shutil
import subprocess
import sys

from buildpack import (
    appdynamics,
    datadog,
    java,
    mxbuild,
    newrelic,
    nginx,
    runtime,
    telegraf,
    util,
)
from buildpack.runtime_components import database
from lib.m2ee.version import MXVersion

BUILDPACK_DIR = os.path.dirname(
    os.path.dirname(os.path.join(os.path.dirname(__file__), ".."))
)
BUILD_DIR = sys.argv[1]
CACHE_DIR = os.path.join(sys.argv[2], "bust")
DOT_LOCAL_LOCATION = os.path.join(BUILD_DIR, ".local")

SUPPORTED_STACKS = [
    "cflinuxfs3",
    None,
]  # None is allowed, but not supported in Cloud V4


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
    except (subprocess.CalledProcessError, UnicodeError, IndexError):
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


def check_database_environment():
    try:
        database.get_config()
        return True
    except RuntimeError as ex:
        logging.error(
            "You should provide a DATABASE_URL by adding a database service "
            "to this application, it can be either MySQL or Postgres "
            "If this is the first push of a new app, "
            "set up a database service "
            "and push again afterwards: %s",
            ex,
        )
        return False


def preflight_check():
    logging.debug("pre-flight-check")
    if not check_database_environment():
        raise Exception("Missing environment variables")

    mx_version_str = runtime.get_version(BUILD_DIR)
    logging.info("Preflight check on version %s", mx_version_str)
    mx_version = MXVersion(str(mx_version_str))
    stack = os.getenv("CF_STACK")
    if not stack in SUPPORTED_STACKS:
        raise Exception("Stack {} is not supported".format(stack))
    if not runtime.check_deprecation(mx_version):
        raise Exception("Version {} is deprecated".format(mx_version_str))


def set_up_directory_structure():
    logging.debug("making directory structure")
    util.mkdir_p(DOT_LOCAL_LOCATION)
    for name in ["runtimes", "log", "database", "data", "bin"]:
        util.mkdir_p(os.path.join(BUILD_DIR, name))
    for name in ["files", "tmp"]:
        util.mkdir_p(os.path.join(BUILD_DIR, "data", name))


def copy_buildpack_resources():
    shutil.copy(
        os.path.join(BUILDPACK_DIR, "etc/m2ee/m2ee.yaml"),
        os.path.join(DOT_LOCAL_LOCATION, "m2ee.yaml"),
    )
    shutil.copytree(
        os.path.join(BUILDPACK_DIR, "etc/nginx"),
        os.path.join(BUILD_DIR, "nginx"),
    )
    shutil.copytree(
        os.path.join(BUILDPACK_DIR, "buildpack"),
        os.path.join(BUILD_DIR, "buildpack"),
    )
    shutil.copytree(
        os.path.join(BUILDPACK_DIR, "lib"), os.path.join(BUILD_DIR, "lib")
    )
    shutil.copy(
        os.path.join(BUILDPACK_DIR, "bin", "mendix-logfilter"),
        os.path.join(BUILD_DIR, "bin", "mendix-logfilter"),
    )


def get_mpr_file():
    return util.get_mpr_file_from_dir(BUILD_DIR)


def is_source_push():
    if get_mpr_file() is not None:
        return True
    else:
        return False


if __name__ == "__main__":
    logging.basicConfig(
        level=util.get_buildpack_loglevel(),
        stream=sys.stdout,
        format="%(levelname)s: %(message)s",
    )

    preflight_check()
    if is_source_push():
        logging.info("Source push detected, starting MxBuild...")
        runtime_version = runtime.get_version(BUILD_DIR)
        mxbuild.compile(
            BUILD_DIR,
            CACHE_DIR,
            DOT_LOCAL_LOCATION,
            runtime_version,
            runtime.get_java_version(runtime_version),
        )
        for folder in ("mxbuild", "mono"):
            path = os.path.join(DOT_LOCAL_LOCATION, folder)
            shutil.rmtree(path, ignore_errors=True)
    set_up_directory_structure()
    copy_buildpack_resources()
    write_current_git_commit()
    java.compile(
        BUILDPACK_DIR,
        CACHE_DIR,
        DOT_LOCAL_LOCATION,
        runtime.get_java_version(runtime.get_version(BUILD_DIR)),
    )
    appdynamics.compile(DOT_LOCAL_LOCATION, CACHE_DIR)
    newrelic.compile(BUILDPACK_DIR, BUILD_DIR)
    telegraf.compile(DOT_LOCAL_LOCATION, CACHE_DIR)
    datadog.compile(DOT_LOCAL_LOCATION, CACHE_DIR)
    runtime.compile(BUILD_DIR, CACHE_DIR)
    nginx.compile(BUILD_DIR, CACHE_DIR)
    logging.info("Mendix Buildpack compile completed")
