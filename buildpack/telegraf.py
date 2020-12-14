# This module adds the Telegraf metrics agent to an app container.
# The agent collects StatsD events from Java agents injected into the runtime (if Datadog is not enabled).
# Additionally, if enabled, PostgreSQL metrics are collected.
# Metrics will be forwarded to either the host defined in APPMETRICS_TARGET environment,
# or to other outputs such as Datadog.

import base64
import json
import logging
import os
import shutil
import subprocess
from distutils.util import strtobool

from jinja2 import Template

from buildpack import datadog, mx_java_agent, util
from buildpack.runtime_components import database

VERSION = "1.16.3"
NAMESPACE = "telegraf"
INSTALL_PATH = os.path.join(os.path.abspath(".local"), NAMESPACE)
EXECUTABLE_PATH = os.path.join(
    INSTALL_PATH, "telegraf-{}".format(VERSION), "usr", "bin", "telegraf"
)
CONFIG_FILE_DIR = os.path.join(
    INSTALL_PATH, "telegraf-{}".format(VERSION), "etc", "telegraf"
)
CONFIG_FILE_PATH = os.path.join(CONFIG_FILE_DIR, "telegraf.conf")
TEMPLATE_FILENAME = "telegraf.toml.j2"
STATSD_PORT = 8125
STATSD_PORT_ALT = 18125

# APPMETRICS_TARGET is a variable which includes JSON (single or array) with the following values:
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
def _get_appmetrics_target():
    return os.getenv("APPMETRICS_TARGET")


def include_db_metrics():
    return strtobool(os.getenv("APPMETRICS_INCLUDE_DB", "true"))


def is_enabled():
    return _get_appmetrics_target() is not None or datadog.is_enabled()


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
    if _get_appmetrics_target():
        try:
            http_configs = json.loads(_get_appmetrics_target())
        except ValueError:
            logging.error(
                "Invalid APPMETRICS_TARGET set. Please check if it contains valid JSON. Telegraf will not forward metrics to InfluxDB."
            )
            return result
        if type(http_configs) is not list:
            http_configs = [http_configs]

    for http_config in http_configs:
        http_output = HttpOutput()
        if "url" not in http_config:
            logging.warning(
                "APPMETRICS_TARGET.url value is not defined in %s. Not adding to Telegraf InfluxDB output configuration.",
                json.dumps(http_config),
            )
        else:
            http_output.url = http_config["url"]

            if "username" in http_config and http_config["username"]:
                # Workaround for https://github.com/influxdata/telegraf/issues/4544
                # http_output['username'] = username
                # http_output['password'] = password
                http_output.credentials = base64.b64encode(
                    (
                        "{}:{}".format(
                            http_config["username"], http_config["password"]
                        )
                    ).encode()
                ).decode("ascii")

            if "kpionly" in http_config and http_config["kpionly"] is not None:
                http_output.kpionly = http_config["kpionly"]

            result.append(http_output)

    return result


def _get_db_config():
    if (
        include_db_metrics() or datadog.get_api_key()
    ) and util.i_am_primary_instance():
        db_config = database.get_config()
        if db_config and db_config["DatabaseType"] == "PostgreSQL":
            return db_config
    return None


def update_config(m2ee, app_name):
    if not is_enabled() or not _is_installed():
        return

    # Populate Telegraf config template
    statsd_port = None
    if mx_java_agent.meets_version_requirements(
        m2ee.config.get_runtime_version()
    ):
        statsd_port = get_statsd_port()

    template_path = os.path.join(CONFIG_FILE_DIR, TEMPLATE_FILENAME)

    tags = util.get_tags()
    if datadog.is_enabled() and "service" not in tags:
        # app and / or service tag not set
        tags["service"] = datadog.get_service()

    with open(template_path, "r") as file_:
        template = Template(file_.read(), trim_blocks=True, lstrip_blocks=True)
    rendered = template.render(
        interval=10,  # in seconds
        tags=tags,
        hostname=util.get_hostname(),
        statsd_port=statsd_port,
        db_config=_get_db_config(),
        database_diskstorage_metric_enabled=datadog.is_database_diskstorage_metric_enabled(),
        database_rate_count_metrics_enabled=datadog.is_database_rate_count_metrics_enabled(),
        datadog_api_key=datadog.get_api_key(),
        datadog_url="{}series/".format(datadog.get_api_url()),
        http_outputs=_get_http_outputs(),
    )

    logging.debug("Writing Telegraf configuration file...")
    with open(CONFIG_FILE_PATH, "w") as file_:
        file_.write(rendered)
    logging.debug("Telegraf configuration file written")


def stage(buildpack_path, build_path, cache_dir):
    if not is_enabled():
        return

    logging.debug("Staging the Telegraf metrics agent...")
    util.download_and_unpack(
        util.get_blobstore_url(
            "/mx-buildpack/telegraf/telegraf-{}_linux_amd64.tar.gz".format(
                VERSION
            )
        ),
        os.path.join(build_path, NAMESPACE),
        cache_dir=cache_dir,
    )

    # Copy the configuration template
    shutil.copy(
        os.path.join(buildpack_path, "etc", "telegraf", TEMPLATE_FILENAME),
        os.path.join(
            build_path,
            NAMESPACE,
            "telegraf-{}".format(VERSION),
            "etc",
            "telegraf",
        ),
    )


def run():
    if not is_enabled():
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
    subprocess.Popen(
        (EXECUTABLE_PATH, "--config", CONFIG_FILE_PATH), env=e,
    )
