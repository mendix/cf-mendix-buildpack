import json
import logging
import os
import socket
import subprocess

import backoff
import yaml

from buildpack import util
from buildpack.runtime_components import database
from buildpack.databroker import is_enabled as is_databroker_enabled
from buildpack.databroker import is_producer_app as is_databroker_producer_app
from buildpack.databroker.config_generator.templates.jmx import (
    consumer,
    kafka_connect,
    kafka_streams,
)

DD_SIDECAR = "cf-datadog-sidecar-v0.21.2_master_103662.tar.gz"
MX_AGENT_JAR = "mx-java-agent.jar"
DD_AGENT_JAR = "dd-java-agent.jar"

SIDECAR_ROOT_DIR = ".local/datadog"
DD_AGENT_DIR = SIDECAR_ROOT_DIR + "/datadog"
DD_AGENT_CONF_DIR = DD_AGENT_DIR + "/etc/datadog-agent"
DD_AGENT_CHECKS_DIR = "/home/vcap/app/datadog_integrations"

DD_LOGS_PORT = 9032


def get_api_key():
    return os.getenv("DD_API_KEY")


def is_enabled():
    return get_api_key() is not None


def _is_dd_tracing_enabled():
    return os.environ.get("DD_TRACE_ENABLED") == "true"


def _is_installed():
    return os.path.exists(DD_AGENT_DIR)


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


def enable_mx_java_agent(m2ee):
    jar = os.path.abspath((SIDECAR_ROOT_DIR + "/{}").format(MX_AGENT_JAR))

    # Check if already configured
    if 0 in [
        v.find("-javaagent:{}".format(jar))
        for v in m2ee.config._conf["m2ee"]["javaopts"]
    ]:
        return

    if m2ee.config.get_runtime_version() >= 7.14:
        agent_config = ""
        agent_config_str = None

        if "METRICS_AGENT_CONFIG" in os.environ:
            agent_config_str = os.environ.get("METRICS_AGENT_CONFIG")
        elif "MetricsAgentConfig" in m2ee.config._conf["mxruntime"]:
            logging.warning(
                "Passing MetricsAgentConfig with Mendix Custom Runtime "
                "Settings is deprecated. "
                "Please use METRICS_AGENT_CONFIG as environment variable."
            )
            agent_config_str = m2ee.config._conf["mxruntime"][
                "MetricsAgentConfig"
            ]

        if agent_config_str:
            try:
                # Ensure that this contains valid JSON
                json.loads(agent_config_str)
                config_file_path = os.path.abspath(
                    ".local/MetricsAgentConfig.json"
                )
                with open(config_file_path, "w") as fh:
                    fh.write(agent_config_str)
                agent_config = "=config=" + config_file_path
            except ValueError:
                logging.error(
                    "Could not parse json from MetricsAgentConfig",
                    exc_info=True,
                )

        m2ee.config._conf["m2ee"]["javaopts"].extend(
            ["-javaagent:{}{}".format(jar, agent_config)]
        )
        # If not explicitly set, default to StatsD
        m2ee.config._conf["mxruntime"].setdefault(
            "com.mendix.metrics.Type", "statsd"
        )


def _enable_dd_java_agent(m2ee):
    jar = os.path.abspath((SIDECAR_ROOT_DIR + "/{}").format(DD_AGENT_JAR))

    # Check if already configured
    if 0 in [
        v.find("-javaagent:{}".format(jar))
        for v in m2ee.config._conf["m2ee"]["javaopts"]
    ]:
        return

    m2ee.config._conf["m2ee"]["javaopts"].extend(["-javaagent:{}".format(jar)])


def _set_up_jmx():
    os.makedirs(DD_AGENT_CHECKS_DIR + "/jmx.d", exist_ok=True)
    with open(DD_AGENT_CHECKS_DIR + "/jmx.d/conf.yaml", "w") as fh:
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
                    "reporter": "statsd:localhost:{}".format(
                        _get_statsd_port()
                    ),
                    'refresh_beans': 120, # runtime takes time to initialize the beans
                    "conf": [
                        {
                            "include": {
                                "bean": "com.mendix:type=SessionInformation",
                                # NamedUsers = 1;
                                # NamedUserSessions = 0;
                                # AnonymousSessions = 0;
                                "attribute": {
                                    "NamedUsers": {"metrics_type": "gauge"},
                                    "NamedUserSessions": {
                                        "metrics_type": "gauge"
                                    },
                                    "AnonymousSessions": {
                                        "metrics_type": "gauge"
                                    },
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
                                    "Transactions": {
                                        "metrics_type": "counter"
                                    },
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
                config["instances"].append(kafka_connect.jmx_metrics)
                config["instances"].append(kafka_streams.jmx_metrics)
            else:
                config["instances"][0]["conf"].extend(consumer.jmx_metrics)

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

        os.makedirs(DD_AGENT_CHECKS_DIR + "/postgres.d", exist_ok=True)
        with open(DD_AGENT_CHECKS_DIR + "/postgres.d/conf.yaml", "w") as fh:
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
    tags = util.get_tags()
    if tags:
        e["DD_TAGS"] = ",".join(tags)
    e["DD_PROCESS_CONFIG_LOG_FILE"] = "/dev/null"
    e["DD_DOGSTATSD_PORT"] = str(_get_statsd_port())

    # Include for forward-compatibility with DD buildpack
    e["DD_ENABLE_CHECKS"] = "true"
    e["DATADOG_DIR"] = str(os.path.abspath(DD_AGENT_DIR))

    return e


def download(install_path, cache_dir):
    util.download_and_unpack(
        util.get_blobstore_url(
            "/mx-buildpack/experimental/{}".format(DD_SIDECAR)
        ),
        os.path.join(install_path, "datadog"),
        cache_dir=cache_dir,
    )


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
                "port": str(DD_LOGS_PORT),
            }
        )

    # Enable Mendix Java Agent
    enable_mx_java_agent(m2ee)

    # Experimental: enable Datadog Java Trace Agent
    # if tracing is explicitly enabled
    if _is_dd_tracing_enabled():
        _enable_dd_java_agent(m2ee)

    # Set up Mendix check
    os.makedirs(DD_AGENT_CHECKS_DIR + "/mendix.d", exist_ok=True)
    with open(DD_AGENT_CHECKS_DIR + "/mendix.d/conf.yaml", "w") as fh:
        config = {
            "logs": [
                {
                    "type": "tcp",
                    "port": str(DD_LOGS_PORT),
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


def stage(install_path, cache_dir):
    if not is_enabled():
        return

    download(install_path, cache_dir)


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
    subprocess.Popen(
        DD_AGENT_DIR + "/run-datadog.sh", env=_set_up_environment()
    )

    # The runtime does not handle a non-open logs endpoint socket
    # gracefully, so wait until it's up
    @backoff.on_predicate(backoff.expo, lambda x: x > 0, max_time=10)
    def _await_logging_endpoint():
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(
            ("localhost", DD_LOGS_PORT)
        )

    logging.info("Awaiting Datadog Agent log subscriber...")
    if _await_logging_endpoint() == 0:
        logging.info("Datadog Agent log subscriber is ready")
    else:
        logging.error(
            "Datadog Agent log subscriber was not initialized correctly."
            "Application logs will not be shipped to Datadog."
        )
