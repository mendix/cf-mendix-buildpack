#
# [EXPERIMENTAL]
#
# Add streams to an app container to collect and optionally filter data
#
import os

from buildpack import util
from buildpack.databroker.process_supervisor import DataBrokerProcess
from buildpack.databroker.config_generator.scripts.generators import (
    stream as stream_generator,
    azkarra as azkarra_generator,
)
from buildpack.databroker.config_generator.scripts.utils import write_file

# Constants
BASE_URL = "/mx-buildpack/experimental/databroker/"
TAR_EXT = "tar"
BASE_DIR = "databroker"
AZKARRA_HOME = os.path.join(BASE_DIR, "azkarra")
AZKARRA_TPLY_CONF_NAME = "topology.conf"
PDR_STREAMS_FILENAME = "stream-sidecar"
PDR_STREAMS_VERSION = "0.18.0"
PDR_STREAMS_DIR = os.path.join(BASE_DIR, "producer-streams")
PDR_STREAMS_HOME = os.path.join(
    PDR_STREAMS_DIR, "{}-{}".format(PDR_STREAMS_FILENAME, PDR_STREAMS_VERSION)
)
LOCAL = ".local"
AZKARRA_CONF_PATH = os.path.join(
    os.getcwd(), LOCAL, PDR_STREAMS_HOME, "azkarra.conf"
)
PROCESS_NAME = "kafka-streams"
KAFKA_STREAMS_JMX_PORT = "11004"
PDR_STREAMS_JAR = os.path.join(
    os.getcwd(),
    LOCAL,
    PDR_STREAMS_HOME,
    "{}-{}.{}".format(PDR_STREAMS_FILENAME, PDR_STREAMS_VERSION, "jar"),
)


def _download_pkgs(install_path, cache_dir):
    # Download producer streams artifact
    PDR_STREAMS_DOWNLOAD_URL = "{}{}-{}.{}".format(
        BASE_URL, PDR_STREAMS_FILENAME, PDR_STREAMS_VERSION, TAR_EXT,
    )
    util.download_and_unpack(
        util.get_blobstore_url(PDR_STREAMS_DOWNLOAD_URL),
        os.path.join(install_path, PDR_STREAMS_DIR),
        cache_dir=cache_dir,
    )


def stage(install_path, cache_dir):
    _download_pkgs(install_path, cache_dir)


def setup_configs(complete_conf):
    TPLY_CONF_PATH = os.path.join(
        os.getcwd(), LOCAL, PDR_STREAMS_HOME, AZKARRA_TPLY_CONF_NAME,
    )
    topologies_config = stream_generator.generate_config(complete_conf)
    write_file(TPLY_CONF_PATH, topologies_config)
    os.environ["TOPOLOGY_CONFIGURATION_PATH"] = TPLY_CONF_PATH

    azkarra_config = azkarra_generator.generate_config(complete_conf)
    write_file(AZKARRA_CONF_PATH, azkarra_config)


def run(complete_conf):
    setup_configs(complete_conf)
    java_path = os.path.join(os.getcwd(), LOCAL, "bin")
    os.environ["PATH"] += os.pathsep + java_path
    os.environ["JMX_PORT"] = KAFKA_STREAMS_JMX_PORT
    env = dict(os.environ)
    kafka_streams_process = DataBrokerProcess(
        PROCESS_NAME,
        (
            "java",
            "-Dconfig.file=" + AZKARRA_CONF_PATH,
            "-Dcom.sun.management.jmxremote",
            "-Dcom.sun.management.jmxremote.authenticate=false",
            "-Dcom.sun.management.jmxremote.ssl=false",
            "-Dcom.sun.management.jmxremote.port=" + KAFKA_STREAMS_JMX_PORT,
            "-jar",
            PDR_STREAMS_JAR,
        ),
        env,
    )
    return kafka_streams_process
