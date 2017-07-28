import os
import re
import json
import errno
import subprocess
import logging
import sys
sys.path.insert(0, 'lib')
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
    patterns = [
        r'(?P<type>[a-zA-Z0-9]+)://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^/]+)/(?P<dbname>[^?]*)(?P<extra>\?.*)?',
        r'jdbc:(?P<type>[a-zA-Z0-9]+)://(?P<host>[^;]+);database=(?P<dbname>[^;]*);user=(?P<user>[^;]+);password=(?P<password>.*)$'
    ]

    supported_databases = {
        'postgres':  'PostgreSQL',
        'postgresql':  'PostgreSQL',
        'mysql': 'MySQL',
        'db2': 'Db2',
        'sqlserver': 'SQLSERVER',
    }

    for pattern in patterns:
        match = re.search(pattern, url)
        if match is not None:
            break
    else:
        raise Exception(
            'Could not parse DATABASE_URL environment variable %s' % url
        )

    database_type_input = match.group('type')
    if database_type_input not in supported_databases:
        raise Exception('Unknown database type: %s', database_type_input)
    database_type = supported_databases[database_type_input]

    config = {
        'DatabaseType': database_type,
        'DatabaseUserName': match.group('user'),
        'DatabasePassword': match.group('password'),
        'DatabaseHost': match.group('host'),
        'DatabaseName': match.group('dbname'),
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
        return {}


def get_database_uri_from_vcap():
    vcap_services = get_vcap_services_data()

    for service_type_name in (
        'p-mysql',
        'p.mysql',
        'elephantsql',
        'cleardb',
        'PostgreSQL',
        'dashDB',
        'mariadb',
        'postgresql',
        'rds',
    ):
        if vcap_services and service_type_name in vcap_services:
            return vcap_services[service_type_name][0]['credentials']['uri']
    if 'azure-sqldb' in vcap_services:
        return vcap_services['azure-sqldb'][0]['credentials']['jdbcUrl']

    for key in vcap_services:
        if key.startswith("rds"):
            return vcap_services[key][0]['credentials']['uri']
        if key.startswith("dashDB"):
            return vcap_services[key][0]['credentials']['uri']

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
    mkdir_p(destination)
    cached_location = os.path.join(cache_dir, file_name)

    logging.debug('Looking for {cached_location}'.format(
        cached_location=cached_location
    ))

    if not os.path.isfile(cached_location):
        download(url, cached_location)
        logging.debug('downloaded to {cached_location}'.format(
            cached_location=cached_location
        ))
    else:
        logging.debug('found in cache: {cached_location}'.format(
            cached_location=cached_location
        ))

    logging.debug('extracting: {cached_location} to {dest}'.format(
        cached_location=cached_location, dest=destination))
    if file_name.endswith('.tar.gz') or file_name.endswith('.tgz'):
        unpack_cmd = ['tar', 'xf', cached_location, '-C', destination]
        if file_name.startswith(('mono-', 'jdk-', 'jre-')):
            unpack_cmd.extend(('--strip', '1'))
        subprocess.check_call(unpack_cmd)
    else:
        raise Exception('do not know how to unpack {cached_location}'.format(
            cached_location=cached_location
        ))

    logging.debug('source {file_name} retrieved & unpacked in {destination}'.format(
        file_name=file_name, destination=destination
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
    logging.debug('downloading {url} to {destination}'.format(
        url=url, destination=destination
    ))
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
    versions = {
        '7': '7u80',
        '8u51': '8u51',
        '8': '8',
    }
    if mx_version >= 6.6:
        default = '8'
    elif mx_version >= 5.18:
        default = '8u51'
    else:
        default = '7'
    main_java_version = os.getenv('JAVA_VERSION', default)

    if main_java_version not in versions.keys():
        raise Exception(
            'Invalid Java version specified: %s'
            % main_java_version
        )
    return versions[main_java_version]


def get_mpr_file_from_dir(directory):
    mprs = filter(lambda x: x.endswith('.mpr'), os.listdir(directory))
    if len(mprs) == 1:
        return os.path.join(directory, mprs[0])
    elif len(mprs) > 1:
        raise Exception('More than one .mpr file found, can not continue')
    else:
        return None


def ensure_mxbuild_in_directory(directory, mx_version, cache_dir):
    if os.path.isdir(os.path.join(directory, 'modeler')):
        return
    mkdir_p(directory)

    url = os.environ.get('FORCED_MXBUILD_URL')
    if url:
        # don't ever cache with a FORCED_MXBUILD_URL
        download_and_unpack(url, directory, cache_dir='/tmp/downloads')
    else:
        try:
            _checkout_from_git_rootfs(directory, mx_version)
        except NotFoundException as e:
            logging.debug(str(e))
            download_and_unpack(
                get_blobstore_url(
                    '/runtime/mxbuild-%s.tar.gz' % str(mx_version)
                ),
                directory, cache_dir=cache_dir
            )


def _checkout_from_git_rootfs(directory, mx_version):
    mendix_runtimes_path = '/usr/local/share/mendix-runtimes.git'
    if not os.path.isdir(mendix_runtimes_path):
        raise NotFoundException()

    env = dict(os.environ)
    env['GIT_WORK_TREE'] = directory

    # checkout the runtime version
    try:
        subprocess.check_call(
            ('git', 'checkout', str(mx_version), '-f'),
            cwd=mendix_runtimes_path, env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return
    except:
        try:
            subprocess.check_call(
                (
                    'git', 'fetch', 'origin',
                    'refs/tags/{0}:refs/tags/{0}'.format(str(mx_version)),
                ),
                cwd=mendix_runtimes_path, env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.check_call(
                ('git', 'checkout', str(mx_version), '-f'),
                cwd=mendix_runtimes_path, env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logging.debug('found mx version after updating runtimes.git')
            return
        except:
            logging.debug('tried updating git repo, also failed')
    raise NotFoundException(
        'Could not download mxbuild ' +
        str(mx_version) +
        ' from updated git repo'
    )


def _get_env_with_monolib(mono_dir):
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = mono_dir + '/lib'
    env['MONO_STRICT_MS_COMPLIANT'] = 'yes'
    if not os.path.isfile(os.path.join(mono_dir, 'lib', 'libgdiplus.so')):
        raise Exception('libgdiplus.so not found in dir %s' % mono_dir)
    return env


def _detect_mono_version(mx_version):
    logging.debug('Detecting Mono Runtime using mendix version: ' + str(mx_version))

    if mx_version < 7:
        target = 'mono-3.10.0'
    else:
        target = 'mono-4.6.2.16'
    logging.info('Selecting Mono Runtime: ' + target)
    return target


def _get_mono_path(directory, mono_version):
    return get_existing_directory_or_raise([
        os.path.join(directory, mono_version),
        '/opt/' + mono_version,
        '/tmp/' + mono_version,
    ], 'Mono not found')


def lazy_remove_file(filename):
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def ensure_and_get_mono(mx_version, cache_dir):
    logging.debug('ensuring mono for mendix {mx_version}'.format(
        mx_version=str(mx_version)
    ))
    mono_version = _detect_mono_version(mx_version)
    fallback_location = '/tmp/opt'
    try:
        mono_location = _get_mono_path('/tmp/opt', mono_version)
    except NotFoundException:
        logging.debug('Mono not found in default locations')
        download_and_unpack(
            get_blobstore_url('/mx-buildpack/' + mono_version + '-mx.tar.gz'),
            os.path.join(fallback_location, mono_version),
            cache_dir
        )
        mono_location = _get_mono_path(fallback_location, mono_version)
    logging.debug('Using {mono_location}'.format(mono_location=mono_location))
    return mono_location


def ensure_and_get_jvm(mx_version, cache_dir, dot_local_location, package='jdk'):
    logging.debug('Begin download and install java %s' % package)
    java_version = get_java_version(mx_version)

    rootfs_java_path = '/usr/lib/jvm/jdk-%s-oracle-x64' % java_version
    if not os.path.isdir(rootfs_java_path):
        logging.debug('rootfs without java sdk detected')
        download_and_unpack(
            get_blobstore_url('/mx-buildpack/%s-%s-linux-x64.tar.gz' % (package, java_version)),
            os.path.join(dot_local_location, 'usr/lib/jvm/%s-%s-oracle-x64' % (package, java_version)),
            cache_dir,
        )
    else:
        logging.debug('rootfs with java sdk detected')
    logging.debug('end download and install java %s' % package)

    return get_existing_directory_or_raise([
        '/usr/lib/jvm/jdk-%s-oracle-x64' % java_version,
        os.path.join(dot_local_location, 'usr/lib/jvm/%s-%s-oracle-x64' % (package, java_version)),
    ], 'Java not found')


def i_am_primary_instance():
    return os.getenv('CF_INSTANCE_INDEX', '0') == '0'
