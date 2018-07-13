#
# [EXPIRIMENTAL]
#
# Add Telegraf to an app container to collect StatsD events from the runtime.
# Metrics will be forwarded to host defined in APPMETRICS_TARGET environment
# variable which is a JSON string with the following values
# - url: complate url of the endpoint. Mandatory.
# - username: basic auth username. Optional.
# - password: basic auth password. Mandatory if username is specified.
#

import json
import os

import buildpackutil
import datadog
import subprocess
from m2ee import logger


def _get_appmetrics_target():
    return os.getenv('APPMETRICS_TARGET')


def is_enabled():
    return _get_appmetrics_target() is not None


def _get_appmetrics_target_url():
    target = json.loads(_get_appmetrics_target())
    if 'url' not in target:
        logger.error('APPMETRICS_TARGET.url value is not defined in %s' % _get_appmetrics_target())
    return target['url']


def _get_appmetrics_target_username():
    target = json.loads(_get_appmetrics_target())
    return target['username'] if 'username' in target else None


def _get_appmetrics_target_password():
    target = json.loads(_get_appmetrics_target())
    return target['password'] if 'password' in target else None


def _config_value_str(value):
    if type(value) is str:
        return '"%s"' % value
    elif type(value) is int:
        return value
    elif type(value) is bool:
        return str(value).lower()
    elif type(value) is list:
        return str([_config_value_str(v) for v in value])


def _write_config(config):
    logger.info('writing config file')
    with open('.local/telegraf/etc/telegraf/telegraf.conf', 'w') as tc:
        for section in config:
            print(section, file=tc)
            for item in config[section]:
                value = config[section][item]
                print('  %s = %s' % (item, _config_value_str(value)), file=tc)

            print('', file=tc)


def _get_tags():
    # Telegraf tags must be key / value
    tags = {}
    for kv in [t.split(':') for t in buildpackutil.get_tags()]:
        if len(kv) == 2:
            tags[kv[0]] = kv[1]
        else:
            logger.warn('Skipping tag % because not a key/value')
    return tags


def _get_http_output_config():
    http_output = {
        'url': _get_appmetrics_target_url(),
        'method': 'POST',
        'data_format': 'influx'
    }
    username = _get_appmetrics_target_username()
    password = _get_appmetrics_target_password()
    if username is not None:
        http_output.username = username
        http_output.password = password
    return http_output


def update_config(m2ee, app_name):
    if not is_enabled():
        return

    # Telegraf config, taking over defaults from telegraf.conf from the distro
    logger.info('creating telegraf config')
    config = {
        '[global_tags]': _get_tags(),
        '[agent]': {
            'interval': '10s',
            'round_interval': True,
            'metric_batch_size': 1000,
            'metric_buffer_limit': 10000,
            'collection_jitter': '0s',
            'flush_jitter': '10s',
            'precision': '',
            'debug': False,
            'logfile': '',
            'hostname': datadog._get_hostname(),
            'omit_hostname': False
        },
        '[[outputs.http]]': _get_http_output_config(),
        '[[inputs.statsd]]': {
            'protocol': 'udp',
            'max_tcp_connections': 250,
            'tcp_keep_alive': False,
            'service_address': ':8125',
            'delete_gauges': True,
            'delete_counters': True,
            'delete_sets': True,
            'delete_timings': True,
            'percentiles': [90],
            'metric_separator': '_',
            'parse_data_dog_tags': True,
            'allowed_pending_messages': 10000,
            'percentile_limit': 1000
        }
    }
    # Forward metrics also to DataDog when enabled
    if datadog.is_enabled():
        config['[[outputs.datadog]]'] = {
            'apikey': datadog.get_api_key()
        }

    _write_config(config)
    datadog.enable_runtime_agent(m2ee)


def compile(install_path, cache_dir):
    if not is_enabled():
        return
    #
    # Add Telegraf to the container which can forward metrics to a custom
    # AppMetrics target
    buildpackutil.download_and_unpack(
        buildpackutil.get_blobstore_url(
            '/mx-buildpack/experimental/dd-v0.8.0.tar.gz',
        ),
        os.path.join(install_path, 'datadog'),
        cache_dir=cache_dir,
    )

    buildpackutil.download_and_unpack(
        'https://dl.influxdata.com/telegraf/releases/telegraf-1.7.1_linux_amd64.tar.gz',
        install_path,
        cache_dir=cache_dir
    )


def run():
    if not is_enabled():
        return
    e = dict(os.environ)
    subprocess.Popen((
        '.local/telegraf/usr/bin/telegraf',
        '--config', '.local/telegraf/etc/telegraf/telegraf.conf'
    ), env=e)
