# This module adds the Datadog IoT and trace agents to the container.
# To replicate the functionality of the full agent, a Telegraf agent is started alongside.
# The following is collected by these two agents:
#
# - Datadog: Application metrics (through the Mendix Java Agent)
# - Datadog: Application logs (through a runtime logs subscriber)
# - Datadog: Application traces, if enabled (through the Datadog Java Agent and Trace Agent)
# - Telegraf: PostgreSQL metrics, replicating the Datadog metric names
# - Telegraf: Database diskstorage size metric

import glob
import json
import logging
import os
import socket
import stat
import subprocess
from collections import OrderedDict
from distutils.util import strtobool

import backoff
import yaml

from buildpack import util
from buildpack.runtime_components import database

NAMESPACE = "datadog"

SIDECAR_VERSION = "4.19.0"
SIDECAR_ARTIFACT_NAME = "datadog-cloudfoundry-buildpack-{}.zip".format(
    SIDECAR_VERSION
)
SIDECAR_URL_ROOT = "/mx-buildpack/{}".format(NAMESPACE)
JAVA_AGENT_VERSION = "0.68.0"
JAVA_AGENT_ARTIFACT_NAME = "dd-java-agent-{}.jar".format(JAVA_AGENT_VERSION)
JAVA_AGENT_URL_ROOT = "/mx-buildpack/{}".format(NAMESPACE)

ROOT_DIR = os.path.abspath(".local")
SIDECAR_ROOT_DIR = os.path.join(ROOT_DIR, NAMESPACE)
AGENT_DIR = os.path.join(SIDECAR_ROOT_DIR, "lib")
AGENT_USER_CHECKS_DIR = os.path.abspath("/home/vcap/app/datadog_integrations")

STATSD_PORT = 8125
LOGS_PORT = 9032


def _get_user_checks_dir():
    os.makedirs(AGENT_USER_CHECKS_DIR, exist_ok=True)
    return AGENT_USER_CHECKS_DIR


def _get_jmx_checks_dir():
    path = os.path.join(_get_user_checks_dir(), "jmx.d")
    os.makedirs(path, exist_ok=True)
    return path


def _get_jmx_conf_file():
    return os.path.join(_get_jmx_checks_dir(), "conf.yaml")


# Returns the Datadog API key in use
def get_api_key():
    return os.getenv("DD_API_KEY")


def _get_site_tld():
    return os.getenv("DD_SITE", "app.datadoghq.com").split(".")[-1]


# Returns the Datadog Metrics API endpoint
def get_api_url():
    return "https://api.datadoghq.{}/api/v1/".format(_get_site_tld())


# Returns whether Datadog is enabled
def is_enabled():
    return get_api_key() is not None


# Toggles Datadog APM
def _is_tracing_enabled():
    return strtobool(os.environ.get("DD_TRACE_ENABLED", "false"))


# Toggles logs redaction (email addresses are replaced by a generic string)
def _is_logs_redaction_enabled():
    return strtobool(os.environ.get("DATADOG_LOGS_REDACTION", "true"))


# Toggles database rare / count metrics which are collected by Telegraf
# By default, they are not compatible with the Datadog Postgres integration due to Telegraf limitations
def is_database_rate_count_metrics_enabled():
    return strtobool(
        os.environ.get("DATADOG_DATABASE_RATE_COUNT_METRICS", "false")
    )


# Toggles the database diskstorage metrics
# It is basically a fixed value based on an environment variable
def is_database_diskstorage_metric_enabled():
    return (
        strtobool(
            os.environ.get("DATADOG_DATABASE_DISKSTORAGE_METRIC", "true")
        )
        and os.environ.get("DATABASE_DISKSTORAGE") is not None
    )


def _is_installed():
    return os.path.exists(AGENT_DIR)


def get_service():
    dd_service_name = os.environ.get("DD_SERVICE_NAME")
    if dd_service_name:
        return dd_service_name
    else:
        service_from_tags = _get_service_from_tags()
        if service_from_tags:
            return service_from_tags
    return util.get_app_from_domain()


def _get_service_from_tags():
    dict_filter = lambda x, y: dict([(i, x[i]) for i in x if i in set(y)])

    service_tags = sorted(
        OrderedDict(dict_filter(util.get_tags(), ("app", "service")),).items(),
        reverse=True,
    )
    if service_tags:
        return service_tags[0][1]
    return None


# Appends user tags with mandatory tags if required
def _get_datadog_tags():
    tags = util.get_tags()
    if not "service" in tags:
        # app and / or service tag not set
        tags["service"] = get_service()

    tags_strings = []
    for k, v in tags.items():
        tags_strings.append("{}:{}".format(k, v))
    return ",".join(tags_strings)


def get_statsd_port():
    return STATSD_PORT


def _set_up_dd_java_agent(m2ee, jmx_config_files):
    jar = os.path.join(SIDECAR_ROOT_DIR, JAVA_AGENT_ARTIFACT_NAME)

    # Check if already configured
    if 0 in [
        v.find("-javaagent:{}".format(jar))
        for v in m2ee.config._conf["m2ee"]["javaopts"]
    ]:
        return

    # Extend with Java Agent and JMX options
    m2ee.config._conf["m2ee"]["javaopts"].extend(
        [
            "-javaagent:{}".format(jar),
            "-D{}={}".format("dd.tags", _get_datadog_tags()),
            "-D{}={}".format("dd.jmxfetch.enabled", "true"),
            "-D{}={}".format("dd.jmxfetch.statsd.port", get_statsd_port()),
        ]
    )

    if jmx_config_files:
        # Set up Java Agent JMX configuration
        m2ee.config._conf["m2ee"]["javaopts"].extend(
            [
                "-D{}={}".format(
                    "dd.jmxfetch.config", ",".join(jmx_config_files)
                ),
            ]
        )

    # Extend with tracing options
    if _is_tracing_enabled():
        m2ee.config._conf["m2ee"]["javaopts"].extend(
            [
                "-D{}={}".format("dd.trace.enabled", "true"),
                "-D{}={}".format("dd.service", get_service()),
                "-D{}={}".format("dd.logs.injection", "true"),
            ]
        )

        # Extend with database service mapping
        dbconfig = database.get_config()
        if dbconfig:
            m2ee.config._conf["m2ee"]["javaopts"].extend(
                [
                    "-D{}={}".format(
                        "dd.service.mapping",
                        "{}:{}.db".format(
                            dbconfig["DatabaseType"].lower(), get_service()
                        ),
                    ),
                ]
            )


def _get_runtime_jmx_config(extra_jmx_instance_config=None):
    # JMX beans and values can be inspected with jmxterm
    # Download the jmxterm jar into the container
    # and run app/.local/bin/java -jar ~/jmxterm.jar
    #
    # The extra attributes are only available from Mendix 7.15.0+
    config = {
        "init_config": {},
        "instances": [
            {
                "jvm_direct": True,
                "name": "mendix_jmx",
                "refresh_beans": 120,  # The runtime takes time to initialize the beans
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

    # Merge extra instance configuration
    if extra_jmx_instance_config:
        config["instances"][0]["conf"].extend(extra_jmx_instance_config)

    return config


def _set_up_environment():

    # Trace variables need to be set in the global environment
    # since the Datadog Java Trace Agent does not live inside the Datadog Agent process

    e = dict(os.environ.copy())

    # Everything in datadog.yaml can be configured with environment variables
    # This is the "official way" of working with the DD buildpack, so let's do this to ensure forward compatibility
    e["DD_API_KEY"] = get_api_key()
    e["DD_HOSTNAME"] = util.get_hostname()

    e["DD_LOG_FILE"] = "/dev/null"
    e["DD_PROCESS_CONFIG_LOG_FILE"] = "/dev/null"
    e["DD_DOGSTATSD_PORT"] = str(get_statsd_port())

    # Transform and append tags
    e["DD_TAGS"] = _get_datadog_tags()
    if "TAGS" in e:
        del e["TAGS"]

    # Set Mendix Datadog sidecar specific environment variables
    # e["DD_ENABLE_USER_CHECKS"] = "true"

    # Set Datadog Cloud Foundry Buildpack specific environment variables
    e["DATADOG_DIR"] = str(AGENT_DIR)
    e["RUN_AGENT"] = "true"
    e["DD_LOGS_ENABLED"] = "true"
    e["DD_ENABLE_CHECKS"] = "false"
    e["LOGS_CONFIG"] = json.dumps(_get_logging_config())

    return e


def _get_logging_config():
    config = [
        {
            "type": "tcp",
            "port": str(LOGS_PORT),
            "source": "mendix",
            "service": get_service(),
        }
    ]

    if _is_logs_redaction_enabled():
        logging.info(
            "Datadog logs redaction enabled, all email addresses will be redacted"
        )
        log_processing_rules = {
            "log_processing_rules": [
                {
                    "type": "mask_sequences",
                    "name": "RFC_5322_email",
                    "pattern": r"""(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])""",
                    "replace_placeholder": "[EMAIL REDACTED]",
                }
            ]
        }
        config[0] = {**config[0], **log_processing_rules}

    return config


def update_config(m2ee, extra_jmx_instance_config=None, jmx_config_files=[]):
    if not is_enabled() or not _is_installed():
        return

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

    # Set up runtime JMX configuration
    with open(_get_jmx_conf_file(), "w") as fh:
        fh.write(
            yaml.safe_dump(
                _get_runtime_jmx_config(
                    extra_jmx_instance_config=extra_jmx_instance_config,
                )
            )
        )

    # Set up Datadog Java Trace Agent
    jmx_config_files.append(_get_jmx_conf_file())
    _set_up_dd_java_agent(
        m2ee, jmx_config_files=jmx_config_files,
    )


def _download(build_path, cache_dir):
    util.download_and_unpack(
        util.get_blobstore_url(
            "{}/{}".format(SIDECAR_URL_ROOT, SIDECAR_ARTIFACT_NAME)
        ),
        os.path.join(build_path, NAMESPACE),
        cache_dir=cache_dir,
        alias="cf-datadog-sidecar",  # Removes the old sidecar if present
    )
    util.download_and_unpack(
        util.get_blobstore_url(
            "{}/{}".format(JAVA_AGENT_URL_ROOT, JAVA_AGENT_ARTIFACT_NAME)
        ),
        os.path.join(build_path, NAMESPACE),
        cache_dir=cache_dir,
        unpack=False,
    )


def stage(buildpack_path, build_path, cache_path):
    if not is_enabled():
        return

    logging.debug("Staging Datadog...")
    _download(build_path, cache_path)

    logging.debug("Setting permissions...")
    files = glob.glob(("{}/*.sh").format(AGENT_DIR))
    for exec_file in files:
        logging.debug("Setting [{}] to be executable...".format(exec_file))
        st = os.stat(exec_file)
        os.chmod(exec_file, st.st_mode | stat.S_IEXEC)


def run():
    if not is_enabled():
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

    agent_environment = _set_up_environment()
    logging.debug(
        "Datadog Agent environment variables: [{}]".format(agent_environment)
    )

    subprocess.Popen(
        os.path.join(AGENT_DIR, "run-datadog.sh"), env=agent_environment
    )

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
