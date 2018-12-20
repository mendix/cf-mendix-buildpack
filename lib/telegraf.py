#
# [EXPERIMENTAL]
#
# Add Telegraf to an app container to collect StatsD events from the runtime.
# Metrics will be forwarded to host defined in APPMETRICS_TARGET environment
# variable which is a JSON (single or array) with the following values
# - url: complete url of the endpoint. Mandatory.
# - username: basic auth username. Optional.
# - password: basic auth password. Mandatory if username is specified.
# - kpionly: indicates that by default only metrics with KPI=true tag are passed
#     to custom end points
#
# Examples:
# {"url": "https://customreceiver.mydomain.com", "username": "user", "password": "secret", "kpionly": true}
# [{"url": "https://customreceiver.mydomain.com", "username": "user", "password": "secret", "kpionly": true}]
#

import base64
import json
import os

import buildpackutil
import datadog
import subprocess
from m2ee import logger


def _get_appmetrics_target():
    return os.getenv("APPMETRICS_TARGET")


def _get_appmetrics_aai():
    return os.getenv("APPMETRICS_AAI")


def is_enabled():
    return _get_appmetrics_target() is not None or _get_appmetrics_aai() is not None


def _is_installed():
    return os.path.exists(".local/telegraf/usr/bin/telegraf")


def _get_tags():
    # Telegraf tags must be key / value
    tags = {}
    for kv in [t.split(":") for t in buildpackutil.get_tags()]:
        if len(kv) == 2:
            tags[kv[0]] = kv[1]
        else:
            logger.warn(
                'Skipping tag "{}" from TAGS because not a key/value'.format(
                    kv[0]
                )
            )
    return tags


def _config_value_str(value):
    if type(value) is str:
        return '"%s"' % value
    elif type(value) is int:
        return value
    elif type(value) is bool:
        return str(value).lower()
    elif type(value) is list:
        return json.dumps(value)


def _create_config_file(agent_config):
    logger.debug("writing config file")
    with open(".local/telegraf/etc/telegraf/telegraf.conf", "w") as tc:
        print("[agent]", file=tc)
        for item in agent_config:
            value = agent_config[item]
            print("  {} = {}".format(item, _config_value_str(value)), file=tc)

        print("", file=tc)


def _write_config(section, config):
    logger.debug("writing section {}".format(section))
    with open(".local/telegraf/etc/telegraf/telegraf.conf", "a") as tc:
        _write_config_in_fd(section, config, tc)


def _write_config_in_fd(section, config, fd, indent=""):
    print("{}{}".format(indent, section), file=fd)
    # reverse sort to get '[section]' in last
    for item in sorted(config, reverse=True):
        value = config[item]
        if type(value) is dict:
            _write_config_in_fd(item, value, fd, "{}  ".format(indent))
        else:
            print(
                "{}  {} = {}".format(indent, item, _config_value_str(value)),
                file=fd,
            )

    print("", file=fd)


def _write_http_output_config(http_config):
    logger.debug("writing http output config")
    if "url" not in http_config:
        logger.error(
            "APPMETRICS_TARGET.url value is not defined in {}".format(
                _get_appmetrics_target()
            )
        )
        return

    http_output = {
        "url": http_config["url"],
        "method": "POST",
        "data_format": "influx",
    }

    username = http_config.get("username")
    password = http_config.get("password")
    if username:
        # Workaround for https://github.com/influxdata/telegraf/issues/4544
        # http_output['username'] = username
        # http_output['password'] = password
        credentials = base64.b64encode(
            ("{}:{}".format(username, password)).encode()
        ).decode("ascii")
        http_output["[outputs.http.headers]"] = {
            "Authorization": "Basic {}".format(credentials)
        }

    kpionly = http_config["kpionly"] if "kpionly" in http_config else True
    if kpionly:
        http_output["[outputs.http.tagpass]"] = {"KPI": ["true"]}

    _write_config("[[outputs.http]]", http_output)


def _write_aai_output_config():
    logger.debug("writing aai output config")
    aai_output = {
        "instrumentation_key": _get_appmetrics_aai(),
    }

    _write_config("[[outputs.application_insights]]", aai_output)


def _write_mendix_admin_http_input_config(action, metric_prefix, query, fields):
    mxpassword = os.getenv("ADMIN_PASSWORD")
    mxpassword64 = base64.b64encode(mxpassword.encode()).decode("ascii")
    http_input = {
        "urls": ["http://localhost:82/_mxadmin"],
        "method": "POST",
        "[inputs.http.headers]": {"Content-Type": "application/json", "X-M2EE-Authentication":  mxpassword64 },
        "data_format": "json",
        "name_override": metric_prefix,
        "body": "{\\\"action\\\" : \\\"" + action + "\\\", \\\"params\\\":{} }",
        "json_query": query,
        "fieldpass": fields
    }
    _write_config("[[inputs.http]]", http_input)

def _write_mendix_admin_http_named_input_config(action, metric_prefix, key_name, query, fields):
    mxpassword = os.getenv("ADMIN_PASSWORD")
    mxpassword64 = base64.b64encode(mxpassword.encode()).decode("ascii")
    http_input = {
        "urls": ["http://localhost:82/_mxadmin"],
        "method": "POST",
        "[inputs.http.headers]": {"Content-Type": "application/json", "X-M2EE-Authentication":  mxpassword64 },
        "data_format": "json",
        "name_prefix": metric_prefix,
        "json_name_key": key_name,
        "body": "{\\\"action\\\" : \\\"" + action + "\\\", \\\"params\\\":{} }",
        "json_query": query,
        "fieldpass": fields
    }
    _write_config("[[inputs.http]]", http_input)

def _write_cpu_input_config():
    cpu_input = {
        "percpu": False,
        "totalcpu": True,
    }
    _write_config("[[inputs.cpu]]", cpu_input)

def update_config(m2ee, app_name):
    if not is_enabled() or not _is_installed():
        return

    # Telegraf config, taking over defaults from telegraf.conf from the distro
    logger.debug("creating telegraf config")
    _create_config_file(
        {
            "interval": "10s",
            "round_interval": True,
            "metric_batch_size": 1000,
            "metric_buffer_limit": 10000,
            "collection_jitter": "0s",
            "flush_jitter": "10s",
            "precision": "",
            "debug": False,
            "logfile": "",
            "hostname": buildpackutil.get_hostname(),
            "omit_hostname": False,
        }
    )

    _write_config("[global_tags]", _get_tags())
    _write_config(
        "[[inputs.statsd]]",
        {
            "protocol": "udp",
            "max_tcp_connections": 250,
            "tcp_keep_alive": False,
            "service_address": ":8125",
            "delete_gauges": True,
            "delete_counters": True,
            "delete_sets": True,
            "delete_timings": True,
            "percentiles": [90],
            "metric_separator": ".",
            "parse_data_dog_tags": True,
            "allowed_pending_messages": 10000,
            "percentile_limit": 1000,
        },
    )

    # Forward metrics also to DataDog when enabled
    if datadog.is_enabled():
        _write_config("[[outputs.datadog]]", {"apikey": datadog.get_api_key()})

    # Expose metrics to Azure Application Insights when enabled
    if _get_appmetrics_aai() is not None:
        _write_aai_output_config()
    
    # Collect statistics from Mendix admin port
    _write_mendix_admin_http_input_config("runtime_statistics", "mendix_runtime_memory", "feedback.memory", ["used_heap", "committed_heap", "init_heap", "max_heap", "used_nonheap", "committed_nonheap", "init_nonheap", "max_nonheap"])
    _write_mendix_admin_http_input_config("runtime_statistics", "mendix_runtime_connectionbus", "feedback.connectionbus", ["select", "insert", "update", "delete", "transaction"])
    _write_mendix_admin_http_input_config("runtime_statistics", "mendix_runtime_sessions", "feedback.sessions", ["named_users", "anonymous_sessions", "named_user_sessions"])
    _write_mendix_admin_http_input_config("server_statistics", "mendix_runtime_threads", "feedback.threadpool", ["threads"])
    _write_mendix_admin_http_input_config("server_statistics", "mendix_runtime_connections", "feedback.jetty", ["current_connections"])
    _write_mendix_admin_http_input_config("get_logged_in_user_names", "mendix_runtime_loggedinusers", "feedback", ["count"])
    _write_mendix_admin_http_named_input_config("runtime_statistics", "mendix_runtime_requests_", "name", "feedback.requests", ["value"])

    _write_cpu_input_config()

    # # Write http_oputs (one or array)
    if _get_appmetrics_target() is not None:
        http_configs = json.loads(_get_appmetrics_target())
        if type(http_configs) is list:
            for http_config in http_configs:
                _write_http_output_config(http_config)
        else:
            _write_http_output_config(http_configs)

    # Enable Java Agent on MxRuntime to
    datadog.enable_runtime_agent(m2ee)


def compile(install_path, cache_dir):
    if not is_enabled():
        return
    #
    # Add Telegraf to the container which can forward metrics to a custom
    # AppMetrics target
    buildpackutil.download_and_unpack(
        buildpackutil.get_blobstore_url(
            "/mx-buildpack/experimental/dd-v0.8.0.tar.gz"
        ),
        os.path.join(install_path, "datadog"),
        cache_dir=cache_dir,
    )

    buildpackutil.download_and_unpack(
        "https://dl.influxdata.com/telegraf/nightlies/telegraf-nightly_linux_amd64.tar.gz",
        install_path,
        cache_dir=cache_dir,
    )


def run():
    if not is_enabled():
        return

    if not _is_installed():
        logger.warn(
            "Telegraf isn't installed yet but APPMETRICS_TARGET is set. "
            + "Please push or restage your app to complete Telegraf installation."
        )
        return

    e = dict(os.environ)
    subprocess.Popen(
        (
            ".local/telegraf/usr/bin/telegraf",
            "--config",
            ".local/telegraf/etc/telegraf/telegraf.conf",
        ),
        env=e,
    )
