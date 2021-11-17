#!/usr/bin/env python3
import logging
import os
import shutil
import sys

from buildpack import databroker, util
from buildpack.core import java, mxbuild, nginx, runtime
from buildpack.infrastructure import database
from buildpack.telemetry import (
    appdynamics,
    datadog,
    dynatrace,
    logs,
    metering,
    mx_java_agent,
    newrelic,
    telegraf,
)

BUILDPACK_DIR = os.path.abspath(
    os.path.dirname(
        os.path.dirname(os.path.join(os.path.dirname(__file__), ".."))
    )
)
BUILD_DIR = os.path.abspath(sys.argv[1])
CACHE_DIR = os.path.abspath(os.path.join(sys.argv[2], "bust"))
DOT_LOCAL_LOCATION = os.path.abspath(os.path.join(BUILD_DIR, ".local"))

SUPPORTED_STACKS = [
    "cflinuxfs3",
    None,
]  # None is allowed, but not supported


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


def preflight_check(version):
    if not check_database_environment():
        raise ValueError("Missing database configuration")

    stack = os.getenv("CF_STACK")
    logging.info(
        "Preflight check on Mendix version [%s] and stack [%s]...",
        version,
        stack,
    )

    if not stack in SUPPORTED_STACKS:
        raise NotImplementedError(
            "Stack [{}] is not supported by this buildpack".format(stack)
        )
    if not runtime.is_version_supported(version):
        raise NotImplementedError(
            "Mendix version [{}] is not supported by this buildpack".format(
                version
            )
        )
    if runtime.is_version_end_of_support(version):
        logging.warning(
            "Mendix version [{}] is end-of-support. Please upgrade to a supported Mendix version (https://docs.mendix.com/releasenotes/studio-pro/lts-mts).".format(
                version
            )
        )
    logging.info("Preflight check completed")


def set_up_directory_structure():
    logging.debug("Creating buildpack directory structure...")
    util.mkdir_p(DOT_LOCAL_LOCATION)


def copy_buildpack_resources():
    shutil.copytree(
        os.path.join(BUILDPACK_DIR, "buildpack"),
        os.path.join(BUILD_DIR, "buildpack"),
    )
    shutil.copytree(
        os.path.join(BUILDPACK_DIR, "lib"), os.path.join(BUILD_DIR, "lib")
    )
    commit_file_path = os.path.join(BUILDPACK_DIR, ".commit")
    if os.path.isfile(commit_file_path):
        shutil.copy(
            commit_file_path,
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

    runtime_version = runtime.get_runtime_version(BUILD_DIR)

    try:
        preflight_check(runtime_version)
    except (ValueError, NotImplementedError) as error:
        logging.error(error)
        exit(1)

    if is_source_push():
        try:
            mxbuild.build_from_source(
                BUILDPACK_DIR,
                BUILD_DIR,
                CACHE_DIR,
                DOT_LOCAL_LOCATION,
                runtime_version,
                runtime.get_java_version(runtime_version),
            )
        except RuntimeError as error:
            logging.error(error)
            exit(1)

    set_up_directory_structure()
    copy_buildpack_resources()
    java.stage(
        BUILDPACK_DIR,
        CACHE_DIR,
        DOT_LOCAL_LOCATION,
        runtime.get_java_version(runtime_version),
    )
    appdynamics.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    dynatrace.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    newrelic.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    mx_java_agent.stage(
        BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR, runtime_version
    )
    telegraf.stage(
        BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR, runtime_version
    )
    datadog.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    metering.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    database.stage(BUILDPACK_DIR, BUILD_DIR)
    runtime.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    logs.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    databroker.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    nginx.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    logging.info("Mendix Cloud Foundry Buildpack staging completed")
