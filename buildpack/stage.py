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
    fluentbit,
    splunk,
    logs,
    metering,
    mx_java_agent,
    newrelic,
    telegraf,
    dynatrace,
)

BUILDPACK_DIR = os.path.abspath(
    os.path.dirname(os.path.dirname(os.path.join(os.path.dirname(__file__), "..")))
)
BUILD_DIR = os.path.abspath(sys.argv[1])
CACHE_DIR = os.path.abspath(os.path.join(sys.argv[2], "bust"))
DOT_LOCAL_LOCATION = os.path.abspath(os.path.join(BUILD_DIR, ".local"))
if len(sys.argv) >= 5:
    DEPS_DIR = os.path.abspath(sys.argv[3])
    DEPS_IDX = os.path.abspath(sys.argv[4])
if len(sys.argv) >= 6 and sys.argv[5] != "":
    PROFILE_DIR = os.path.abspath(sys.argv[5])
else:
    PROFILE_DIR = os.path.abspath(os.path.join(BUILD_DIR, ".profile.d"))

SUPPORTED_STACKS = [
    "cflinuxfs4",
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

    if stack not in SUPPORTED_STACKS:
        raise NotImplementedError(f"Stack [{stack}] is not supported by this buildpack")
    if not runtime.is_version_implemented(version):
        raise NotImplementedError(
            "Mendix [{version.major}] is not supported by this buildpack"
        )
    if not runtime.is_version_supported(version):
        logging.warning(
            "Mendix [%s] is end-of-support. Please use a supported Mendix version "
            "(https://docs.mendix.com/releasenotes/studio-pro/lts-mts).",
            version.major,
        )
    elif not runtime.is_version_maintained(version):
        logging.info(
            "Mendix [%d.%d] is not maintained. Please use a medium- or long-term "
            "supported Mendix version to easily receive fixes "
            "(https://docs.mendix.com/releasenotes/studio-pro/lts-mts).",
            version.major,
            version.minor,
        )

    logging.info("Preflight check completed")


def set_up_directory_structure():
    logging.debug("Creating buildpack directory structure...")
    util.mkdir_p(DOT_LOCAL_LOCATION)


def set_up_launch_environment():
    logging.debug("Creating buildpack launch environment...")
    util.mkdir_p(PROFILE_DIR)
    util.set_up_launch_environment(DEPS_DIR, PROFILE_DIR)


def copy_buildpack_resources():
    shutil.copytree(
        os.path.join(BUILDPACK_DIR, "buildpack"),
        os.path.join(BUILD_DIR, "buildpack"),
    )
    shutil.copytree(os.path.join(BUILDPACK_DIR, "lib"), os.path.join(BUILD_DIR, "lib"))
    commit_file_path = os.path.join(BUILDPACK_DIR, ".commit")
    if os.path.isfile(commit_file_path):
        shutil.copy(
            commit_file_path,
            os.path.join(BUILD_DIR, ".commit"),
        )
    version_file_path = os.path.join(BUILDPACK_DIR, "VERSION")
    if os.path.isfile(version_file_path):
        shutil.copy(
            version_file_path,
            os.path.join(BUILD_DIR, "VERSION"),
        )


def copy_dependency_file():
    shutil.copy(
        os.path.join(BUILDPACK_DIR, util.DEPENDENCY_FILE),
        os.path.join(BUILD_DIR, util.DEPENDENCY_FILE),
    )


def get_mpr_file():
    return util.get_mpr_file_from_dir(BUILD_DIR)


def is_source_push():
    if get_mpr_file() is not None:
        return True
    return False


def cleanup_dependency_cache(cached_dir, dependency_list):
    # get directory structure
    for root, dirs, files in os.walk(cached_dir):
        for file in files:
            file_full_path = os.path.join(root, file)
            logging.debug("dependency in cache folder: [%s]", file_full_path)
            if file_full_path not in dependency_list:
                # delete from cache
                os.remove(file_full_path)
                logging.debug(
                    "deleted unused dependency [%s] from [%s]...", file_full_path, root
                )


if __name__ == "__main__":
    util.initialize_globals()

    logging.basicConfig(
        level=util.get_buildpack_loglevel(),
        stream=sys.stdout,
        format="%(levelname)s: %(message)s",
    )

    runtime_version = runtime.get_runtime_version(BUILD_DIR)
    JAVA_VERSION = java.get_java_major_version(runtime_version)

    try:
        preflight_check(runtime_version)
    except (ValueError, NotImplementedError) as error:
        logging.error(error)
        sys.exit(1)

    copy_dependency_file()

    if is_source_push():
        try:
            mxbuild.build_from_source(
                BUILDPACK_DIR,
                BUILD_DIR,
                CACHE_DIR,
                DOT_LOCAL_LOCATION,
                runtime_version,
                JAVA_VERSION,
            )
        except RuntimeError as error:
            logging.error(error)
            sys.exit(1)

    set_up_directory_structure()
    copy_buildpack_resources()
    set_up_launch_environment()

    java.stage(
        BUILDPACK_DIR,
        CACHE_DIR,
        DOT_LOCAL_LOCATION,
        JAVA_VERSION,
    )
    appdynamics.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    dynatrace.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    splunk.stage()
    newrelic.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    fluentbit.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    mx_java_agent.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR, runtime_version)
    telegraf.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR, runtime_version)
    datadog.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    metering.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    database.stage(BUILDPACK_DIR, BUILD_DIR)
    runtime.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    logs.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    databroker.stage(BUILDPACK_DIR, DOT_LOCAL_LOCATION, CACHE_DIR)
    nginx.stage(BUILDPACK_DIR, BUILD_DIR, CACHE_DIR)
    logging.info("Mendix Cloud Foundry Buildpack staging completed")

    cleanup_dependency_cache(CACHE_DIR, util.CACHED_DEPENDENCIES)
