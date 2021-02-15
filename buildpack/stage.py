#!/usr/bin/env python3
import logging
import os
import shutil
import sys

from buildpack import (
    appdynamics,
    dynatrace,
    databroker,
    datadog,
    java,
    metering,
    mx_java_agent,
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


def preflight_check(runtime_version):
    if not check_database_environment():
        raise ValueError("Missing environment variables")

    stack = os.getenv("CF_STACK")
    logging.info(
        "Preflight check on Mendix runtime version [%s] and stack [%s]...",
        runtime_version,
        stack,
    )

    if not stack in SUPPORTED_STACKS:
        raise NotImplementedError("Stack [{}] is not supported".format(stack))
    if not runtime.check_deprecation(runtime_version):
        raise NotImplementedError(
            "Mendix runtime version [{}] is not supported".format(
                runtime_version
            )
        )
    logging.info("Preflight check completed")


def set_up_directory_structure():
    logging.debug("Creating directory structure...")
    util.mkdir_p(DOT_LOCAL_LOCATION)
    for name in ["runtimes", "log", "database", "data", "bin", ".postgresql"]:
        util.mkdir_p(os.path.join(BUILD_DIR, name))
    for name in ["files", "tmp", "database"]:
        util.mkdir_p(os.path.join(BUILD_DIR, "data", name))


def copy_buildpack_resources():
    shutil.copytree(
        os.path.join(BUILDPACK_DIR, "buildpack"),
        os.path.join(BUILD_DIR, "buildpack"),
    )
    shutil.copytree(
        os.path.join(BUILDPACK_DIR, "lib"), os.path.join(BUILD_DIR, "lib")
    )
    shutil.copy(
        os.path.join(BUILDPACK_DIR, ".commit"),
        os.path.join(BUILD_DIR, ".commit"),
    )
    shutil.copy(
        os.path.join(BUILDPACK_DIR, "VERSION"),
        os.path.join(BUILD_DIR, "VERSION"),
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

    runtime_version = runtime.get_version(BUILD_DIR)

    try:
        preflight_check(runtime_version)
    except (ValueError, NotImplementedError) as error:
        logging.error(error)
        exit(1)

    if is_source_push():
        logging.info("Source push detected, starting MxBuild...")
        try:
            mxbuild.stage(
                BUILD_DIR,
                CACHE_DIR,
                DOT_LOCAL_LOCATION,
                runtime_version,
                runtime.get_java_version(runtime_version),
            )
        except RuntimeError as error:
            logging.error(error)
            exit(1)
        finally:
            for folder in ("mxbuild", "mono"):
                path = os.path.join(DOT_LOCAL_LOCATION, folder)
                shutil.rmtree(path, ignore_errors=True)

    set_up_directory_structure()
    copy_buildpack_resources()
    java.stage(
        BUILDPACK_DIR,
        CACHE_DIR,
        DOT_LOCAL_LOCATION,
        runtime.get_java_version(runtime.get_version(BUILD_DIR)),
    )
    appdynamics.stage(DOT_LOCAL_LOCATION, CACHE_DIR)
    dynatrace.stage(DOT_LOCAL_LOCATION, CACHE_DIR)
    newrelic.stage(DOT_LOCAL_LOCATION, CACHE_DIR)
    mx_java_agent.stage(DOT_LOCAL_LOCATION, CACHE_DIR, runtime_version)
    telegraf.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    datadog.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    metering.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    runtime.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    databroker.stage(DOT_LOCAL_LOCATION, CACHE_DIR)
    nginx.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    logging.info("Mendix Cloud Foundry Buildpack staging completed")
