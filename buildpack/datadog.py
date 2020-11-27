import logging
import os
import shutil
import socket
import subprocess
from distutils.util import strtobool

import backoff
import yaml

from buildpack import util
from buildpack.databroker import is_enabled as is_databroker_enabled
from buildpack.databroker import is_producer_app as is_databroker_producer_app
from buildpack.databroker.config_generator.scripts.generators import (
    jmx as jmx_cfg_generator,
)
from buildpack.databroker.config_generator.scripts.utils import write_file
from buildpack.databroker.config_generator.templates.jmx import consumer
from buildpack.runtime_components import database

NAMESPACE = "datadog"

SIDECAR_VERSION = "v0.22.0"
SIDECAR_ARCHIVE = "cf-datadog-sidecar-{}.tar.gz".format(SIDECAR_VERSION)
JAVA_AGENT_VERSION = "0.68.0"
JAVA_AGENT_JAR = "dd-java-agent-{}.jar".format(JAVA_AGENT_VERSION)
SIDECAR_URL_ROOT = "/mx-buildpack/experimental"
JAVA_AGENT_URL_ROOT = "/mx-buildpack/{}".format(NAMESPACE)

ROOT_DIR = os.path.abspath(".local")
SIDECAR_ROOT_DIR = os.path.join(ROOT_DIR, NAMESPACE)
AGENT_DIR = os.path.join(SIDECAR_ROOT_DIR, "datadog")
AGENT_CONF_DIR = os.path.join(AGENT_DIR, "etc", "datadog-agent")
AGENT_CHECKS_CONF_DIR = os.path.abspath("/home/vcap/app/datadog_integrations")

LOGS_PORT = 9032


def get_api_key():
    return os.getenv("DD_API_KEY")


def is_enabled():
    return get_api_key() is not None


def _is_dd_tracing_enabled():
    return strtobool(os.environ.get("DD_TRACE_ENABLED", "false"))


def _is_installed():
    return os.path.exists(AGENT_DIR)


def _get_service():
    return os.environ.get("DD_SERVICE_NAME", _get_application())


def _get_application():
    app_tags = list(filter(lambda x: "app:" in x, util.get_tags()))
    if app_tags:
        return app_tags[0].split(":")[1]
    else:
        return util.get_appname()


def _get_statsd_port():
    if util.is_appmetrics_enabled():
        return 18125
    else:
        return 8125


def _enable_dd_java_agent(m2ee):
    if _is_dd_tracing_enabled():
        jar = os.path.join(SIDECAR_ROOT_DIR, JAVA_AGENT_JAR)

        # Check if already configured
        if 0 in [
            v.find("-javaagent:{}".format(jar))
            for v in m2ee.config._conf["m2ee"]["javaopts"]
        ]:
            return

        m2ee.config._conf["m2ee"]["javaopts"].extend(
            ["-javaagent:{}".format(jar)]
        )


def _is_database_diskstorage_enabled():
    return strtobool(
        os.environ.get("DD_ENABLE_DATABASE_DISKSTORAGE_CHECK", "true")
    )


def _set_up_database_diskstorage():
    # Enables the Mendix database diskstorage check
    # This check is a very dirty workaround
    # and makes an environment variable into a gauge with a fixed value.
    if _is_database_diskstorage_enabled():
        with open(
            AGENT_CHECKS_CONF_DIR + "mx_database_diskstorage.yml", "w"
        ) as fh:
            config = {
                "init_config": {},
                "instances": [{"min_collection_interval": 15}],
            }


def _set_up_jmx():
    runtime_jmx_dir = AGENT_CHECKS_CONF_DIR + "/jmx.d"
    # JMX beans and values can be inspected with jmxterm
    # Download the jmxterm jar into the container
    # and run app/.local/bin/java -jar ~/jmxterm.jar
    #
    # The extra attributes are only available from Mendix 7.15.0+
    config = {
        "init_config": {"collect_default_metrics": True, "is_jmx": True},
        "instances": [
            {
                "host": "localhost",
                "port": 7845,
                "java_bin_path": str(os.path.abspath(".local/bin/java")),
                "java_options": "-Xmx50m -Xms5m",
                "reporter": "statsd:localhost:{}".format(_get_statsd_port()),
                "refresh_beans": 120,  # runtime takes time to initialize the beans
                "conf": [
                    {
                        "include": {
                            "bean": "com.mendix:type=SessionInformation",
                            # NamedUsers = 1;
                            # NamedUserSessions = 0;
                            # AnonymousSessions = 0;
                            "attribute": {
                                "NamedUsers": {"metrics_type": "gauge"},
                                "NamedUserSessions": {"metrics_type": "gauge"},
                                "AnonymousSessions": {"metrics_type": "gauge"},
                            },
                        }
                    },
                    {
                        "include": {
                            "bean": "com.mendix:type=Statistics,name=DataStorage",
                            # Selects = 1153;
                            # Inserts = 1;
                            # Updates = 24;
                            # Deletes = 0;
                            # Transactions = 25;
                            "attribute": {
                                "Selects": {"metrics_type": "counter"},
                                "Updates": {"metrics_type": "counter"},
                                "Inserts": {"metrics_type": "counter"},
                                "Deletes": {"metrics_type": "counter"},
                                "Transactions": {"metrics_type": "counter"},
                            },
                        }
                    },
                    {
                        "include": {
                            "bean": "com.mendix:type=General",
                            # Languages = en_US;
                            # Entities = 24;
                            "attribute": {
                                "Entities": {"metrics_type": "gauge"}
                            },
                        }
                    },
                    {
                        "include": {
                            "bean": "com.mendix:type=JettyThreadPool",
                            # Threads = 8
                            # IdleThreads = 3;
                            # IdleTimeout = 60000;
                            # MaxThreads = 254;
                            # StopTimeout = 30000;
                            # MinThreads = 8;
                            # ThreadsPriority = 5;
                            # QueueSize = 0;
                            "attribute": {
                                "Threads": {"metrics_type": "gauge"},
                                "MaxThreads": {"metrics_type": "gauge"},
                                "IdleThreads": {"metrics_type": "gauge"},
                                "QueueSize": {"metrics_type": "gauge"},
                            },
                        }
                    },
                ],
                #  }, {
                #    'include': {
                #        'bean': 'com.mendix:type=Jetty',
                #        # ConnectedEndPoints = 0;
                #        # IdleTimeout = 30000;
                #        # RequestsActiveMax = 0;
                #        'attribute': {
                #        }
                #    },
            }
        ],
    }

    if is_databroker_enabled():
        if is_databroker_producer_app():
            runtime_jmx_dir = AGENT_CHECKS_CONF_DIR + "/jmx_1.d"

            # kafka connect cfg
            os.makedirs(AGENT_CHECKS_CONF_DIR + "/jmx_2.d", exist_ok=True)
            kafka_connect_cfg = (
                jmx_cfg_generator.generate_kafka_connect_jmx_config()
            )
            write_file(
                AGENT_CHECKS_CONF_DIR + "/jmx_2.d/conf.yaml", kafka_connect_cfg
            )

            # kafka streams cfg
            os.makedirs(AGENT_CHECKS_CONF_DIR + "/jmx_3.d", exist_ok=True)
            kafka_streams_cfg = (
                jmx_cfg_generator.generate_kafka_streams_jmx_config()
            )
            write_file(
                AGENT_CHECKS_CONF_DIR + "/jmx_3.d/conf.yaml", kafka_streams_cfg
            )
        else:
            config["instances"][0]["conf"].extend(consumer.jmx_metrics)

    os.makedirs(runtime_jmx_dir, exist_ok=True)
    with open(runtime_jmx_dir + "/conf.yaml", "w") as fh:
        fh.write(yaml.safe_dump(config))


def _set_up_postgres():
    # TODO: set up a way to disable this, on shared database (mxapps.io) we
    # don't want to allow this.
    if not util.i_am_primary_instance():
        return
    dbconfig = database.get_config()
    if dbconfig:
        for k in (
            "DatabaseType",
            "DatabaseUserName",
            "DatabasePassword",
            "DatabaseHost",
        ):
            if k not in dbconfig:
                logging.warning(
                    "Skipping database configuration for Datadog because "
                    "configuration is not found. See database_config.py "
                    "for details"
                )
                return
        if dbconfig["DatabaseType"] != "PostgreSQL":
            return

        os.makedirs(AGENT_CHECKS_CONF_DIR + "/postgres.d", exist_ok=True)
        with open(AGENT_CHECKS_CONF_DIR + "/postgres.d/conf.yaml", "w") as fh:
            config = {
                "init_config": {},
                "instances": [
                    {
                        "host": dbconfig["DatabaseHost"].split(":")[0],
                        "port": int(dbconfig["DatabaseHost"].split(":")[1]),
                        "username": dbconfig["DatabaseUserName"],
                        "password": dbconfig["DatabasePassword"],
                        "dbname": dbconfig["DatabaseName"],
                    }
                ],
            }
            fh.write(yaml.safe_dump(config))


def _set_up_environment():

    # Trace variables need to be set in the global environment
    # since the Datadog Java Trace Agent does not live inside the Datadog Agent process
    if _is_dd_tracing_enabled():
        os.environ["DD_SERVICE_NAME"] = _get_service()
        os.environ["DD_JMXFETCH_ENABLED"] = "false"
        dbconfig = database.get_config()
        if dbconfig:
            os.environ["DD_SERVICE_MAPPING"] = "{}:{}.db".format(
                dbconfig["DatabaseType"].lower(), _get_service()
            )

    e = dict(os.environ.copy())

    # Everything in datadog.yaml can be configured with environment variables
    # This is the "official way" of working with the DD buildpack, so let's do this to ensure forward compatibility
    e["DD_API_KEY"] = get_api_key()
    e["DD_HOSTNAME"] = util.get_hostname()

    # Explicitly turn off tracing to ensure backward compatibility
    if not _is_dd_tracing_enabled():
        e["DD_TRACE_ENABLED"] = "false"
    e["DD_LOGS_ENABLED"] = "true"
    e["DD_LOG_FILE"] = "/dev/null"
    e["DD_PROCESS_CONFIG_LOG_FILE"] = "/dev/null"
    e["DD_DOGSTATSD_PORT"] = str(_get_statsd_port())

    # Enable configured checks
    e["DD_ENABLE_USER_CHECKS"] = "true"

    e["DATADOG_DIR"] = str(AGENT_DIR)

    return e


def update_config(m2ee):
    if (
        not is_enabled()
        or not _is_installed()
        or m2ee.config.get_runtime_version() < 7.14
    ):
        return

    # Set up JVM JMX
    m2ee.config._conf["m2ee"]["javaopts"].extend(
        [
            "-Dcom.sun.management.jmxremote",
            "-Dcom.sun.management.jmxremote.port=7845",
            "-Dcom.sun.management.jmxremote.local.only=true",
            "-Dcom.sun.management.jmxremote.authenticate=false",
            "-Dcom.sun.management.jmxremote.ssl=false",
            "-Djava.rmi.server.hostname=127.0.0.1",
        ]
    )

    # Set up runtime logging
    if m2ee.config.get_runtime_version() >= 7.15:
        m2ee.config._conf["logging"].append(
            {
                "type": "tcpjsonlines",
                "name": "DatadogSubscriber",
                "autosubscribe": "INFO",
                "host": "localhost",
                # For MX8 integer is supported again, this change needs to be
                # made when MX8 is GA
                "port": str(LOGS_PORT),
            }
        )

    # Experimental: enable Datadog Java Trace Agent
    # if tracing is explicitly enabled
    _enable_dd_java_agent(m2ee)

    # Set up Mendix checks
    _set_up_database_diskstorage()
    os.makedirs(AGENT_CHECKS_CONF_DIR + "/mendix.d", exist_ok=True)
    with open(AGENT_CHECKS_CONF_DIR + "/mendix.d/conf.yaml", "w") as fh:
        config = {
            "logs": [
                {
                    "type": "tcp",
                    "port": str(LOGS_PORT),
                    "service": _get_service(),
                    "source": "mendix",
                    "tags": util.get_tags(),
                }
            ]
        }
        fh.write(yaml.safe_dump(config))

    # Set up embedded checks
    _set_up_jmx()
    _set_up_postgres()


def _download(build_path, cache_dir):
    util.download_and_unpack(
        util.get_blobstore_url(
            "{}/{}".format(SIDECAR_URL_ROOT, SIDECAR_ARCHIVE)
        ),
        os.path.join(build_path, NAMESPACE),
        cache_dir=cache_dir,
    )
    util.download_and_unpack(
        util.get_blobstore_url(
            "{}/{}".format(JAVA_AGENT_URL_ROOT, JAVA_AGENT_JAR)
        ),
        os.path.join(build_path, NAMESPACE),
        cache_dir=cache_dir,
        unpack=False,
    )


def _copy_files(buildpack_path, build_path):
    file_name = "mx_database_diskstorage.py"
    shutil.copyfile(
        os.path.join(buildpack_path, "etc", NAMESPACE, "checks.d", file_name),
        os.path.join(
            build_path,
            NAMESPACE,
            "datadog",
            "etc",
            "datadog-agent",
            "checks.d",
            file_name,
        ),
    )


def stage(buildpack_path, build_path, cache_path):
    if not is_enabled():
        return

    _download(build_path, cache_path)
    _copy_files(buildpack_path, build_path)


def run(runtime_version):
    if not is_enabled():
        return

    if runtime_version < 7.14:
        logging.warning(
            "Datadog integration requires Mendix 7.14 or newer. "
            "The Datadog Agent is not enabled."
        )
        return

    if not _is_installed():
        logging.warning(
            "Datadog Agent isn't installed yet but DD_API_KEY is set."
            "Please push or restage your app to complete Datadog installation."
        )
        return

    # Start the run script "borrowed" from the official DD buildpack
    # and include settings as environment variables
    logging.info("Starting Datadog Agent...")
    subprocess.Popen(AGENT_DIR + "/run-datadog.sh", env=_set_up_environment())

    # The runtime does not handle a non-open logs endpoint socket
    # gracefully, so wait until it's up
    @backoff.on_predicate(backoff.expo, lambda x: x > 0, max_time=10)
    def _await_logging_endpoint():
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(
            ("localhost", LOGS_PORT)
        )

    logging.info("Awaiting Datadog Agent log subscriber...")
    if _await_logging_endpoint() == 0:
        logging.info("Datadog Agent log subscriber is ready")
    else:
        logging.error(
            "Datadog Agent log subscriber was not initialized correctly."
            "Application logs will not be shipped to Datadog."
        )
