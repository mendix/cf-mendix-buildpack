import os
import re
import json


def get_database_config(development_mode=False):
    url = os.environ['DATABASE_URL']
    pattern = r'([a-zA-Z]+)://([^:]+):([^@]+)@([^/]+)/(.*)'
    match = re.search(pattern, url)
    supported_databases = {
        'postgres':  'PostgreSQL',
        'mysql': 'MySQL',
    }

    if match is None:
        raise Exception(
            'Could not parse DATABASE_URL environment variable %s' % url
        )

    database_type_input = match.group(1)
    if database_type_input not in supported_databases:
        raise Exception('Unknown database type: %s', database_type_input)
    database_type = supported_databases[database_type_input]

    config = {
        'DatabaseType': database_type,
        'DatabaseUserName': match.group(2),
        'DatabasePassword': match.group(3),
        'DatabaseHost': match.group(4),
        'DatabaseName': match.group(5),
    }
    if development_mode:
        config.update({
            'ConnectionPoolingMaxIdle': 1,
            'ConnectionPoolingMaxActive': 4,
            'ConnectionPoolingNumTestsPerEvictionRun': 50,
            'ConnectionPoolingSoftMinEvictableIdleTimeMillis': 1000,
            'ConnectionPoolingTimeBetweenEvictionRunsMillis': 1000,
        })
    elif database_type_input == 'mysql':
        config.update({
            'ConnectionPoolingNumTestsPerEvictionRun': 50,
            'ConnectionPoolingSoftMinEvictableIdleTimeMillis': 10000,
            'ConnectionPoolingTimeBetweenEvictionRunsMillis': 10000,
        })

    add_config_when_set(config, 'ConnectionPoolingMaxIdle')
    add_config_when_set(config, 'ConnectionPoolingMaxActive')
    add_config_when_set(config, 'ConnectionPoolingMinIdle')
    add_config_when_set(config, 'ConnectionPoolingMinActive')

    return config


def add_config_when_set(config, config_name):
    value = os.environ.get(config_name)
    if not value is None:
        config[config_name] = value


def get_vcap_services_data():
    if os.environ.get('VCAP_SERVICES'):
        return json.loads(os.environ.get('VCAP_SERVICES'))
    else:
        return None


def get_new_relic_license_key():
    vcap_services = get_vcap_services_data()
    if vcap_services and 'newrelic' in vcap_services:
        return vcap_services['newrelic'][0]['credentials']['licenseKey']
    return None
