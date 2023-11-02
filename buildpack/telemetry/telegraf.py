# This module adds the Telegraf metrics agent to an app container.
# The agent collects StatsD events from Java agents injected into the runtime
# (if Datadog is not enabled).
# Additionally, if enabled, PostgreSQL metrics are collected.
# Metrics will be forwarded to either the host defined in APPMETRICS_TARGET
# environment, or to other outputs such as Datadog.

import base64
import json
import logging
import os
import shutil
import subprocess

from buildpack import util
from buildpack.core import runtime
from buildpack.infrastructure import database
from lib.m2ee.util import strtobool
from jinja2 import Template

from . import appdynamics, datadog, dynatrace, metrics, mx_java_agent, newrelic, splunk

NAMESPACE = "telegraf"
DEPENDENCY = f"{NAMESPACE}.agent"
INSTALL_PATH = os.path.join(os.path.abspath(".local"), NAMESPACE)


def _get_executable_path(version):
    return os.path.join(INSTALL_PATH, f"telegraf-{version}", "usr", "bin", "telegraf")


def _get_config_file_dir(version):
    return os.path.join(INSTALL_PATH, f"telegraf-{version}", "etc", "telegraf")


def _get_config_file_path(version):
    return os.path.join(_get_config_file_dir(version), "telegraf.conf")


TEMPLATE_FILENAME = "telegraf.toml.j2"

APPDYNAMICS_OUTPUT_SCRIPT_PATH = os.path.join(
    os.getcwd(),
    "buildpack",
    "telemetry",
    "appdynamics_telegraf_output.py",
)

POSTGRES_METRICS_INTERVAL = int(os.getenv("POSTGRES_METRICS_INTERVAL", default="10"))

STATSD_PORT = 8125
STATSD_PORT_ALT = 18125

# APPMETRICS_TARGET is a variable which includes JSON (single or array)
# with the following values:
# - url: complete url of the endpoint. Mandatory.
# - username: basic auth username. Optional.
# - password: basic auth password. Mandatory if username is specified.
# - kpionly: indicates that by default only metrics with KPI=true tag
#            are passed to custom end points
#
# Examples:
# {
#  "url": "https://customreceiver.mydomain.com",
#  "username": "user",
#  "password": "secret",
#  "kpionly": true
# }
# [{
#  "url": "https://customreceiver.mydomain.com",
#  "username": "user",
#   "password": "secret",
#   "kpionly": true
# }]


def include_db_metrics():
    if metrics.deny_all_apm_metrics():
        return False
    if util.is_free_app():
        # For free apps we are not interested in database metrics
        return False

    result = False
    is_appmetrics = metrics.get_appmetrics_target() is not None

    if (
        is_appmetrics
        or datadog.is_enabled()
        or appdynamics.machine_agent_enabled()
        or dynatrace.is_telegraf_enabled()
        or newrelic.is_enabled()
    ):
        # For customers who have Datadog or AppDynamics or APPMETRICS_TARGET enabled,
        # we always include the database metrics. They can opt out
        # using the APPMETRICS_INCLUDE_DB flag
        result = strtobool(os.getenv("APPMETRICS_INCLUDE_DB", "true"))

    return result


def _get_app_index():
    return int(os.getenv("CF_INSTANCE_INDEX", "0"))


def is_enabled(runtime_version):
    return (
        metrics.get_appmetrics_target() is not None
        or datadog.is_enabled()
        or appdynamics.machine_agent_enabled()
        or dynatrace.is_telegraf_enabled()
        or metrics.micrometer_metrics_enabled(runtime_version)
        or newrelic.is_enabled()
    )


def _is_installed():
    return os.path.exists(INSTALL_PATH)


def get_statsd_port():
    return STATSD_PORT


class HttpOutput:
    def __init__(self):
        self.url = None
        self.credentials = None
        self.kpionly = True


def _get_http_outputs():
    http_configs = []
    result = []
    if metrics.get_appmetrics_target():
        try:
            http_configs = json.loads(metrics.get_appmetrics_target())
        except ValueError:
            logging.error(
                "Invalid APPMETRICS_TARGET set. "
                "Please check if it contains valid JSON. "
                "Telegraf will not forward metrics to InfluxDB."
            )
            return result
        if not isinstance(http_configs, list):
            http_configs = [http_configs]

    for http_config in http_configs:
        http_output = HttpOutput()
        if "url" not in http_config:
            logging.warning(
                "APPMETRICS_TARGET.url value is not defined in %s. "
                "Not adding to Telegraf InfluxDB output configuration.",
                json.dumps(http_config),
            )
        else:
            http_output.url = http_config["url"]

            if "username" in http_config and http_config["username"]:
                # Workaround for https://github.com/influxdata/telegraf/issues/4544
                # http_output['username'] = username
                # http_output['password'] = password
                http_output.credentials = base64.b64encode(
                    (f"{http_config['username']}:{http_config['password']}").encode()
                ).decode("ascii")

            if "kpionly" in http_config and http_config["kpionly"] is not None:
                http_output.kpionly = http_config["kpionly"]

            result.append(http_output)

    return result


def _get_db_config():
    if include_db_metrics() and util.is_cluster_leader():
        db_config = database.get_config()
        if db_config and db_config["DatabaseType"] == "PostgreSQL":
            return db_config
    return None


def _get_dynatrace_config(app_name):
    token, ingest_url = dynatrace.get_ingestion_info()
    tags = util.get_tags()
    return {
        "token": token,
        "ingest_url": ingest_url,
        "dimensions": {
            "app": app_name,
            "instance_index": _get_app_index(),
            **tags,
        },
    }


def _fix_metrics_registries_config(m2ee):
    # Metrics.Registries is a nested JSON entry. As a result, when we read
    # from the environment, it is not a list of registries but a string.
    # We fix it here so that it is a list.
    try:
        metrics_registries_value = util.get_custom_runtime_setting(
            m2ee, metrics.METRICS_REGISTRIES_KEY
        )
    except KeyError:
        # Move on if we do not have the key set
        return

    try:
        current_registries = json.loads(metrics_registries_value)
    except TypeError:
        # Type error indicates the value is not a string and we can
        # then ignore it and continue
        current_registries = metrics_registries_value

    # Update the registries with the fixed set of entries
    util.upsert_custom_runtime_setting(
        m2ee,
        metrics.METRICS_REGISTRIES_KEY,
        current_registries,
        overwrite=True,
    )


def _get_integration_usages():
    """
    Collects usage information of third-party integrations.
    We emit these information via telegraf for internal monitoring
    """
    integration_usages = {}
    checker_methods = {
        "datadog": datadog.is_enabled,
        "dynatrace": dynatrace.is_telegraf_enabled,
        "appdynamics": appdynamics.appdynamics_used,
        "splunk": splunk.is_splunk_enabled,
        "newrelic": newrelic.is_enabled,
    }

    for integration, is_enabled in checker_methods.items():
        if is_enabled():
            integration_usages[integration] = 1

    return integration_usages


def update_config(m2ee, app_name):
    runtime_version = runtime.get_runtime_version()
    if not is_enabled(runtime_version) or not _is_installed():
        return

    # Populate Telegraf config template
    statsd_port = None
    if mx_java_agent.meets_version_requirements(runtime_version):
        statsd_port = get_statsd_port()

    version = util.get_dependency(DEPENDENCY)["version"]

    template_path = os.path.join(_get_config_file_dir(version), TEMPLATE_FILENAME)

    tags = util.get_tags()

    if datadog.is_enabled() and "service" not in tags:
        # app and / or service tag not set
        tags["service"] = datadog.get_service_tag()

    # Add application tags to the custom metrics sent to New Relic
    if newrelic.is_enabled():
        newrelic_tags = newrelic.get_metrics_tags(app_name)
        newrelic_tags["runtime_version"] = runtime_version
        newrelic_tags["model_version"] = runtime.get_model_version()

        # Make sure the user defined values persist, if the tags overlap
        newrelic_tags.update(tags)
        tags = newrelic_tags

    dynatrace_token, dynatrace_ingest_url = dynatrace.get_ingestion_info()

    with open(template_path, "r") as file_:
        template = Template(file_.read(), trim_blocks=True, lstrip_blocks=True)
    rendered = template.render(
        interval=10,  # in seconds
        postgres_metrics_interval=POSTGRES_METRICS_INTERVAL,
        tags=tags,
        hostname=util.get_hostname(),
        statsd_port=statsd_port,
        db_config=_get_db_config(),
        database_diskstorage_metric_enabled=datadog.is_database_diskstorage_metric_enabled(),
        database_rate_count_metrics_enabled=datadog.is_database_rate_count_metrics_enabled(),
        datadog_api_key=datadog.get_api_key(),
        datadog_api_url=f"{datadog.get_api_url()}series/",
        http_outputs=_get_http_outputs(),
        trends_storage_url=metrics.get_micrometer_metrics_url(),
        micrometer_metrics=metrics.micrometer_metrics_enabled(runtime_version),
        cf_instance_index=_get_app_index(),
        app_name=app_name,
        # For Telegraf config only AppDynamics Machine Agent makes sense.
        appdynamics_enabled=appdynamics.machine_agent_enabled(),
        appdynamics_output_script_path=APPDYNAMICS_OUTPUT_SCRIPT_PATH,
        dynatrace_enabled=dynatrace.is_telegraf_enabled(),
        dynatrace_config=_get_dynatrace_config(app_name),
        newrelic_enabled=newrelic.is_enabled(),
        newrelic_config=newrelic.get_metrics_config(),
        telegraf_debug_enabled=os.getenv("TELEGRAF_DEBUG_ENABLED", "false"),
        telegraf_fileout_enabled=strtobool(
            os.getenv("TELEGRAF_FILEOUT_ENABLED", "false")
        ),
        runtime_version=runtime_version,
        integration_usages=_get_integration_usages(),
    )

    logging.debug("Writing Telegraf configuration file...")
    with open(_get_config_file_path(version), "w") as file_:
        file_.write(rendered)
    logging.debug("Telegraf configuration file written")

    logging.debug("Update runtime configuration for metrics registry... ")
    _fix_metrics_registries_config(m2ee)
    util.upsert_custom_runtime_setting(
        m2ee,
        metrics.METRICS_REGISTRIES_KEY,
        metrics.configure_metrics_registry(m2ee),
        overwrite=True,
        append=True,
    )


def stage(buildpack_path, build_path, cache_dir, runtime_version):
    if not is_enabled(runtime_version):
        return

    logging.debug("Staging the Telegraf metrics agent...")
    dependency = util.resolve_dependency(
        DEPENDENCY,
        os.path.join(build_path, NAMESPACE),
        buildpack_dir=buildpack_path,
        cache_dir=cache_dir,
    )

    # Copy the configuration template
    shutil.copy(
        os.path.join(buildpack_path, "etc", "telegraf", TEMPLATE_FILENAME),
        os.path.join(
            build_path,
            NAMESPACE,
            f"telegraf-{dependency['version']}",
            "etc",
            "telegraf",
        ),
    )


def run(runtime_version):
    if not is_enabled(runtime_version):
        return

    if not _is_installed():
        logging.warning(
            "Telegraf isn't installed yet. "
            "Please redeploy your application to "
            "complete Telegraf installation."
        )
        return

    logging.info("Starting the Telegraf metrics agent...")
    e = dict(os.environ)

    version = util.get_dependency(DEPENDENCY)["version"]

    subprocess.Popen(
        (
            _get_executable_path(version),
            "--config",
            _get_config_file_path(version),
        ),
        env=e,
    )
