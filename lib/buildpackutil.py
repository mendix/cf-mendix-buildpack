import os
import re
import json
import errno
import subprocess
import logging
import sys
sys.path.insert(0, 'lib')
from m2ee.version import MXVersion
import requests


def get_database_config(development_mode=False):
    if any(map(
            lambda x: x.startswith('MXRUNTIME_Database'),
            os.environ.keys()
    )):
        return {}

    url = get_database_uri_from_vcap()
    if url is None:
        url = os.environ['DATABASE_URL']
    pattern = r'([a-zA-Z]+)://([^:]+):([^@]+)@([^/]+)/([^?]*)(\?.*)?'

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
            'ConnectionPoolingMaxActive': 20,
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

    return config


def get_vcap_services_data():
    if os.environ.get('VCAP_SERVICES'):
        return json.loads(os.environ.get('VCAP_SERVICES'))
    else:
        return None


def get_database_uri_from_vcap():
    vcap_services = get_vcap_services_data()
    if vcap_services and 'p-mysql' in vcap_services:
        return vcap_services['p-mysql'][0]['credentials']['uri']
    elif 'cleardb' in vcap_services:
        return vcap_services['cleardb'][0]['credentials']['uri']
    elif 'PostgreSQL' in vcap_services:
        return vcap_services['PostgreSQL'][0]['credentials']['uri']
    return None


def appdynamics_used():
    for k, v in os.environ.iteritems():
        if k.startswith('APPDYNAMICS_'):
            return True
    return False


def get_new_relic_license_key():
    vcap_services = get_vcap_services_data()
    if vcap_services and 'newrelic' in vcap_services:
        return vcap_services['newrelic'][0]['credentials']['licenseKey']
    return None


def get_blobstore_url(filename):
    main_url = os.environ.get('BLOBSTORE', 'http://cdn.mendix.com')
    if main_url[-1] == '/':
        main_url = main_url[0:-1]
    return main_url + filename


def download_and_unpack(url, destination, cache_dir='/tmp/downloads'):
    file_name = url.split('/')[-1]
    mkdir_p(cache_dir)
    cached_location = os.path.join(cache_dir, file_name)

    logging.info('preparing {file_name}'.format(file_name=file_name))

    if not os.path.isfile(cached_location):
        logging.info('downloading {file_name}'.format(file_name=file_name))
        download(url, cached_location)
    else:
        logging.debug('already present in cache {file_name}'.format(
            file_name=file_name
        ))

    if file_name.endswith('.deb'):
        subprocess.check_call(
            ['dpkg-deb', '-x', cached_location, destination]
        )
    elif file_name.endswith('.tar.gz') or file_name.endswith('.tgz'):
        subprocess.check_call(
            ['tar', 'xf', cached_location, '-C', destination]
        )
    else:
        raise Exception('do not know how to unpack {file_name}'.format(
            file_name=file_name
        ))

    logging.debug('source {file_name} retrieved & unpacked'.format(
        file_name=file_name
    ))


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def get_buildpack_loglevel():
    if os.getenv('BUILDPACK_XTRACE', 'false') == 'true':
        return logging.DEBUG
    else:
        return logging.INFO


def download(url, destination):
    logging.debug('downloading {url}'.format(url=url))
    with open(destination, 'w') as file_handle:
        response = requests.get(url, stream=True)
        if not response.ok:
            response.raise_for_status()
        for block in response.iter_content(4096):
            if not block:
                break
            file_handle.write(block)


def get_existing_directory_or_raise(dirs, error):
    for directory in dirs:
        if os.path.isdir(directory):
            return directory
    raise NotFoundException(error)


class NotFoundException(Exception):
    pass


def get_java_version(mx_version):
    if type(mx_version) is not MXVersion:
        raise Exception('Type should be MXVersion')

    versions = {
        '7': '7u80',
        '8': '8u45',
    }
    if mx_version >= 5.18:
        default = '8'
    else:
        default = '7'
    main_java_version = os.getenv('JAVA_VERSION', default)

    if main_java_version not in versions.keys():
        raise Exception(
            'Invalid Java version specified: %s'
            % main_java_version
        )
    return versions[main_java_version]
