# This module adds the Datadog IoT and trace agents to the container.
# To replicate the functionality of the full agent, a Telegraf agent is started.
# The following is collected by these two agents:
#
# - Datadog: Application metrics (through the Mendix Java Agent)
# - Datadog: Application logs (through a runtime logs subscriber)
# - Datadog: Application traces, if enabled (through the Datadog Java Agent
#            and Trace Agent)
# - Telegraf: PostgreSQL metrics, replicating the Datadog metric names
# - Telegraf: Database diskstorage size metric

import json
import logging
import os
import socket
import subprocess
from collections import OrderedDict

import backoff
import yaml
from buildpack import util
from buildpack.core import runtime
from buildpack.infrastructure import database
from lib.m2ee.version import MXVersion
from lib.m2ee.util import strtobool

NAMESPACE = "datadog"
TRACE_AGENT_DEPENDENCY = f"{NAMESPACE}.trace-agent"

ROOT_DIR = os.path.abspath(".local")
SIDECAR_ROOT_DIR = os.path.join(ROOT_DIR, NAMESPACE)
AGENT_USER_CHECKS_DIR = os.path.abspath("/home/vcap/app/datadog_integrations")

STATSD_PORT = 8125
LOGS_PORT = 9032


def _get_agent_dir(root=ROOT_DIR):
    return os.path.join(root, NAMESPACE, "lib")


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
    return f"https://api.datadoghq.{_get_site_tld()}/api/v1/"


# Returns whether Datadog is enabled
def is_enabled():
    return get_api_key() is not None


# Toggles Datadog APM
def _is_tracing_enabled():
    return strtobool(os.environ.get("DD_TRACE_ENABLED", "false"))


# Toggles logs redaction (email addresses are replaced by a generic string)
def _is_logs_redaction_enabled():
    """Check if logs should be redacted."""

    # Use this, if it is set
    logs_redaction = os.getenv("LOGS_REDACTION")
    if logs_redaction is not None:
        return strtobool(logs_redaction)

    # Turned on by default
    # DEPRECATED - Datadog-specific LOGS_REDACTION variable
    return strtobool(os.environ.get("DATADOG_LOGS_REDACTION", "true"))


# Toggles database rare / count metrics which are collected by Telegraf
# By default, they are not compatible with the Datadog Postgres integration
# due to Telegraf limitations
def is_database_rate_count_metrics_enabled():
    return strtobool(os.environ.get("DATADOG_DATABASE_RATE_COUNT_METRICS", "false"))


# Toggles the database diskstorage metrics
# It is basically a fixed value based on an environment variable
def is_database_diskstorage_metric_enabled():
    return (
        strtobool(os.environ.get("DATADOG_DATABASE_DISKSTORAGE_METRIC", "true"))
        and os.environ.get("DATABASE_DISKSTORAGE") is not None
    )


# Toggles the system checks. Note that these may not mean anything as they
# might show the host metrics instead of the container metrics.
def _is_checks_enabled():
    return strtobool(os.environ.get("DD_ENABLE_CHECKS", "false"))


# Toggles Datadog profiling. Can only enabled when using AdoptOpenJDK and
# when tracing is enabled.
def _is_profiling_enabled(runtime_version):
    if runtime_version < MXVersion("7.23.1") or not _is_tracing_enabled():
        return False
    return strtobool(os.environ.get("DD_PROFILING_ENABLED", "false"))


def _is_installed():
    return os.path.exists(_get_agent_dir())


def _get_tag_from_env(tag, env_var, default):
    dd_env = os.environ.get(env_var)
    if dd_env:
        return dd_env
    else:
        tags = util.get_tags()
        if tag in tags:
            return tags[tag]
    return default


def get_env_tag():
    return _get_tag_from_env("env", "DD_ENV", "none")


def get_service_tag():
    dd_service = os.environ.get("DD_SERVICE", os.environ.get("DD_SERVICE_NAME"))
    if dd_service:
        return dd_service
    else:
        service_from_tags = _get_service_from_tags()
        if service_from_tags:
            return service_from_tags
    return util.get_app_from_domain()


def _get_service_from_tags():
    dict_filter = lambda x, y: dict(  # noqa: E731
        [(i, x[i]) for i in x if i in set(y)]
    )

    service_tags = sorted(
        OrderedDict(
            dict_filter(util.get_tags(), ("app", "service")),
        ).items(),
        reverse=True,
    )
    if service_tags:
        return service_tags[0][1]
    return None


def get_version_tag(model_version="unversioned"):
    return _get_tag_from_env("version", "DD_VERSION", model_version)


# Appends user tags with mandatory tags if required
def _get_datadog_tags(model_version):
    tags = util.get_tags()
    if "env" not in tags:
        tags["env"] = get_env_tag()
    if "service" not in tags:
        tags["service"] = get_service_tag()
    if "version" not in tags:
        tags["version"] = get_version_tag(model_version)

    tags_strings = []
    for k, v in tags.items():
        tags_strings.append(f"{k}:{v}")
    return ",".join(tags_strings)


def get_statsd_port():
    return int(os.getenv("DD_DOGSTATSD_PORT", str(STATSD_PORT)))


def _set_up_dd_java_agent(m2ee, model_version, runtime_version, jmx_config_files):
    jar = os.path.join(
        SIDECAR_ROOT_DIR,
        os.path.basename(util.get_dependency(TRACE_AGENT_DEPENDENCY)["artifact"]),
    )

    # Check if already configured
    if 0 in [v.find(f"-javaagent:{jar}") for v in util.get_javaopts(m2ee)]:
        return

    # Inject Datadog Java agent
    # Add tags and explicit reserved tags
    util.upsert_javaopts(
        m2ee,
        [
            f"-javaagent:{jar}",
            f"-Ddd.tags={_get_datadog_tags(model_version)}",
            f"-Ddd.env={get_env_tag()}",
            f"-Ddd.service={get_service_tag()}",
            f"-Ddd.version={get_version_tag(model_version)}",
        ],
    )

    # Expllicitly set tracing flag
    util.upsert_javaopts(
        m2ee, f"-Ddd.trace.enabled={str(bool(_is_tracing_enabled())).lower()}"
    )

    # Explicitly set profiling flag
    util.upsert_javaopts(
        m2ee,
        f"-Ddd.profiling.enabled={str(bool(_is_profiling_enabled(runtime_version))).lower()}",
    )

    # Extend with tracing options
    if _is_tracing_enabled():
        util.upsert_javaopts(
            m2ee,
            "-Ddd.logs.injection=true",
        )

        # Extend with database service mapping
        dbconfig = database.get_config()
        if dbconfig and "postgres" in dbconfig["DatabaseType"].lower():
            util.upsert_javaopts(
                m2ee, f"-Ddd.service.mapping=postgresql:{get_service_tag()}.db"
            )

    # Extend with JMX options
    util.upsert_javaopts(
        m2ee,
        [
            "-Ddd.jmxfetch.enabled=true",
            f"-Ddd.jmxfetch.statsd.port={get_statsd_port()}",
        ],
    )

    if jmx_config_files:
        # Set up Java Agent JMX configuration
        util.upsert_javaopts(
            m2ee,
            f"-Ddd.jmxfetch.config={','.join(jmx_config_files)}",
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
                            "attribute": {"Entities": {"metrics_type": "gauge"}},
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


def _set_up_environment(model_version, runtime_version):
    e = dict(os.environ.copy())

    # Everything in datadog.yaml can be configured with environment variables
    # This is the "official way" of working with the DD buildpack
    # so let's do this to ensure forward compatibility
    # Trace variables need to be set in the global environment
    # since the Datadog Java Trace Agent does not live inside the Datadog Agent process
    e["DD_API_KEY"] = get_api_key()
    e["DD_HOSTNAME"] = util.get_hostname()

    e["DD_LOG_FILE"] = "/dev/null"
    e["DD_PROCESS_CONFIG_LOG_FILE"] = "/dev/null"
    e["DD_DOGSTATSD_PORT"] = str(get_statsd_port())

    # Transform and append tags
    e["DD_TAGS"] = _get_datadog_tags(model_version)
    if "TAGS" in e:
        del e["TAGS"]

    # Explicitly add reserved tags
    e["DD_ENV"] = get_env_tag()
    e["DD_VERSION"] = get_version_tag(model_version)
    e["DD_SERVICE"] = get_service_tag()
    if "DD_SERVICE_NAME" in e:
        del e["DD_SERVICE_NAME"]

    # Explicitly enable or disable tracing and profiling
    e["DD_TRACE_ENABLED"] = str(bool(_is_tracing_enabled())).lower()
    e["DD_PROFILING_ENABLED"] = str(
        bool(_is_profiling_enabled(runtime_version))
    ).lower()

    # Set Datadog Cloud Foundry Buildpack specific environment variables
    e["DATADOG_DIR"] = str(_get_agent_dir())
    e["RUN_AGENT"] = "true"
    e["DD_LOGS_ENABLED"] = "true"
    e["DD_ENABLE_CHECKS"] = str(bool(_is_checks_enabled())).lower()
    e["LOGS_CONFIG"] = json.dumps(_get_logging_config())

    return e


def _get_logging_config():
    config = {
        "type": "tcp",
        "port": str(LOGS_PORT),
        "source": "mendix",
        "service": get_service_tag(),
    }

    # Standard rules for e.g. credential redaction
    rules = [
        {
            "type": "mask_sequences",
            "name": "postgres_credentials",
            "pattern": r"\'jdbc:postgresql://(.*)\'",
            "replace_placeholder": "[SECRET REDACTED]",
        },
        {
            "type": "mask_sequences",
            "name": "s3_location",
            "pattern": r"S3 storage, bucket location: (.*)",
            "replace_placeholder": "[SECRET REDACTED]",
        },
        {
            "type": "mask_sequences",
            "name": "s3_endpoint",
            "pattern": r"Endpoint set to: s3-(.*)",
            "replace_placeholder": "[SECRET REDACTED]",
        },
    ]

    # Optional redaction rules; can be toggled with an environment variable
    if _is_logs_redaction_enabled():
        logging.info(
            "Datadog logs redaction enabled, all email addresses will be redacted"
        )

        rules.append(
            {
                "type": "mask_sequences",
                "name": "RFC_5322_email",
                "pattern": r"""(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])""",  # noqa: C0301
                "replace_placeholder": "[EMAIL REDACTED]",
            }
        )

    log_processing_rules = {"log_processing_rules": rules}

    config = {**config, **log_processing_rules}

    return [config]


def update_config(
    m2ee,
    model_version,
    runtime_version,
    extra_jmx_instance_config=None,
    jmx_config_files=None,
):
    if jmx_config_files is None:
        jmx_config_files = []
    if not is_enabled() or not _is_installed():
        return

    # Set up runtime logging
    if runtime.get_runtime_version() >= 7.15:
        util.upsert_logging_config(
            m2ee,
            {
                "type": "tcpjsonlines",
                "name": "DatadogSubscriber",
                "autosubscribe": "INFO",
                "host": "localhost",
                # For MX8 integer is supported again, this change needs to be
                # made when MX8 is GA
                "port": str(LOGS_PORT),
            },
        )

    # Set up runtime JMX configuration
    with open(_get_jmx_conf_file(), "w") as file_handler:
        file_handler.write(
            yaml.safe_dump(
                _get_runtime_jmx_config(
                    extra_jmx_instance_config=extra_jmx_instance_config,
                )
            )
        )

    # Set up Datadog Java Trace Agent
    jmx_config_files.append(_get_jmx_conf_file())
    _set_up_dd_java_agent(
        m2ee,
        model_version,
        runtime_version,
        jmx_config_files=jmx_config_files,
    )


def _download(buildpack_dir, build_path, cache_dir):
    util.resolve_dependency(
        f"{NAMESPACE}.buildpack",
        os.path.join(build_path, NAMESPACE),
        buildpack_dir=buildpack_dir,
        cache_dir=cache_dir,
    )
    util.resolve_dependency(
        TRACE_AGENT_DEPENDENCY,
        os.path.join(build_path, NAMESPACE),
        buildpack_dir=buildpack_dir,
        cache_dir=cache_dir,
        unpack=False,
    )


def _patch_run_datadog_script(script_dir):
    # The Datadog CF buildpack includes a stop routine which bases itself
    # on the Datadog agent being started before the main buildpack process.
    # This works great in multi-buildpack scenarios where the environment variables
    # are set while deploying the application.
    #
    # This is not the case here, and we cannot use the official method since we're
    # setting Datadog environment variables at start, and the agent runs before start.
    # Also, the stop_datadog call assumes a different PID than present, causing a kill
    # call to fail. This applies to all Datadog buildpack versions > 4.20.0.
    #
    # Therefore, the stop_datadog call needs to be patched out.
    # This should be removed when we start using multi-buildpacks
    script = os.path.join(script_dir, "run-datadog.sh")
    with open(script, "r+") as file_handler:
        lines = file_handler.readlines()
        file_handler.seek(0)
        for line in lines:
            if "stop_datadog &" in line:
                file_handler.write(f"# {line}")
            else:
                file_handler.write(line)
        file_handler.truncate()


def stage(buildpack_path, build_path, cache_path):
    if not is_enabled():
        return

    logging.debug("Staging Datadog...")
    _download(buildpack_path, build_path, cache_path)

    logging.debug("Setting Datadog Agent script permissions if required...")
    util.set_executable(f"{_get_agent_dir(build_path)}/*.sh")

    logging.debug("Patching run-datadog.sh...")
    _patch_run_datadog_script(_get_agent_dir(build_path))


def run(model_version, runtime_version):
    if not is_enabled():
        return

    if not _is_installed():
        logging.warning(
            "Datadog Agent isn't installed yet but DD_API_KEY is set."
            "Please push or restage your app to complete Datadog installation."
        )
        return

    logging.debug("Setting Datadog Agent script permissions if required...")
    util.set_executable(f"{_get_agent_dir()}/*.sh")

    # Start the run script "borrowed" from the official DD buildpack
    # and include settings as environment variables
    logging.info("Starting Datadog Agent...")

    agent_environment = _set_up_environment(model_version, runtime_version)
    logging.debug("Datadog Agent environment variables: [%s]", agent_environment)

    subprocess.Popen(
        os.path.join(_get_agent_dir(), "run-datadog.sh"), env=agent_environment
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
