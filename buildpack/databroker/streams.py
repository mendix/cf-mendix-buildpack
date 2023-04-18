"""
[EXPERIMENTAL]

Add streams to an app container to collect and optionally filter data
"""
import os
import logging

from buildpack import util
from buildpack.databroker.process_supervisor import DataBrokerProcess
from buildpack.databroker.config_generator.scripts.generators import (
    stream as stream_generator,
    azkarra as azkarra_generator,
)
from buildpack.databroker.config_generator.scripts.utils import write_file

# Constants
NAMESPACE = BASE_DIR = "databroker"
DEPENDENCY = f"{NAMESPACE}.stream-sidecar"
AZKARRA_TPLY_CONF_NAME = "topology.conf"
PDR_STREAMS_FILENAME = "stream-sidecar"
PDR_STREAMS_DIR = os.path.join(BASE_DIR, "producer-streams")
PROCESS_NAME = "kafka-streams"
KAFKA_STREAMS_JMX_PORT = "11004"
LOCAL = ".local"
LOG_LEVEL = "DEBUG" if util.get_buildpack_loglevel() == logging.DEBUG else "INFO"


def get_pdr_stream_version():
    streams_version = os.getenv("DATABROKER_STREAMS_VERSION")
    if not streams_version:
        streams_version = util.get_dependency(DEPENDENCY)["version"]
    return streams_version


def _get_pdr_streams_home(version):
    return os.path.join(PDR_STREAMS_DIR, f"{PDR_STREAMS_FILENAME}-{version}")


def _get_azkarra_conf_path(version):
    return os.path.join(
        os.getcwd(), LOCAL, _get_pdr_streams_home(version), "azkarra.conf"
    )


def _get_pdr_streams_jar(version):
    return os.path.join(
        os.getcwd(),
        LOCAL,
        _get_pdr_streams_home(version),
        "lib",
        f"{PDR_STREAMS_FILENAME}-{get_pdr_stream_version()}.jar",
    )


def _download_pkgs(buildpack_dir, install_path, cache_dir):
    # Download producer streams artifact
    overrides = {}
    version = os.getenv("DATABROKER_STREAMS_VERSION")
    if version:
        overrides = {"version": version}
    util.resolve_dependency(
        DEPENDENCY,
        os.path.join(install_path, PDR_STREAMS_DIR),
        buildpack_dir=buildpack_dir,
        cache_dir=cache_dir,
        overrides=overrides,
    )


def stage(buildpack_dir, install_path, cache_dir):
    _download_pkgs(buildpack_dir, install_path, cache_dir)


def setup_configs(complete_conf, version):
    TPLY_CONF_PATH = os.path.join(
        os.getcwd(),
        LOCAL,
        _get_pdr_streams_home(version),
        AZKARRA_TPLY_CONF_NAME,
    )
    topologies_config = stream_generator.generate_config(complete_conf)
    write_file(TPLY_CONF_PATH, topologies_config)
    os.environ["TOPOLOGY_CONFIGURATION_PATH"] = TPLY_CONF_PATH

    azkarra_config = azkarra_generator.generate_config(complete_conf)
    write_file(_get_azkarra_conf_path(version), azkarra_config)


def run(complete_conf):
    version = get_pdr_stream_version()
    setup_configs(complete_conf, version)
    java_path = os.path.join(os.getcwd(), LOCAL, "bin")
    os.environ["PATH"] += os.pathsep + java_path
    os.environ["JMX_PORT"] = KAFKA_STREAMS_JMX_PORT
    os.environ["LOG_LEVEL"] = LOG_LEVEL
    env = dict(os.environ)

    kafka_streams_process = DataBrokerProcess(
        PROCESS_NAME,
        (
            "java",
            "-Dconfig.file=" + _get_azkarra_conf_path(version),
            "-Dcom.sun.management.jmxremote",
            "-Dcom.sun.management.jmxremote.authenticate=false",
            "-Dcom.sun.management.jmxremote.ssl=false",
            "-Dcom.sun.management.jmxremote.port=" + KAFKA_STREAMS_JMX_PORT,
            "-jar",
            _get_pdr_streams_jar(version),
        ),
        env,
    )
    return kafka_streams_process
