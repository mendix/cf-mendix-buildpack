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
    mkdir_p(destination)
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


def get_mpr_file_from_dir(directory):
    mprs = filter(lambda x: x.endswith('.mpr'), os.listdir(directory))
    if len(mprs) == 1:
        return os.path.join(directory, mprs[0])
    elif len(mprs) > 1:
        raise Exception('More than one .mpr file found, can not continue')
    else:
        return None


def ensure_mxbuild_in_directory(directory, mx_version, cache_dir):
    if type(mx_version) is not MXVersion:
        raise Exception('Type should be MXVersion')

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
    if type(mx_version) is not MXVersion:
        raise Exception('Type should be MXVersion')

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
        )
        return
    except:
        try:
            subprocess.check_call(
                ('git', 'fetch', '--tags'),
                cwd=mendix_runtimes_path, env=env
            )
            subprocess.check_call(
                ('git', 'checkout', str(mx_version), '-f'),
                cwd=mendix_runtimes_path, env=env
            )
            return
        except:
            logging.debug('tried updating git repo, also failed')
    raise NotFoundException(
        'Could not download mxbuild ' +
        str(mx_version) +
        ' from updated git repo'
    )


def fix_mono_config_and_get_env(mono_lib_dir):
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = mono_lib_dir
    subprocess.check_call([
        'sed',
        '-i',
        's|/app/vendor/mono/lib/libgdiplus.so|%s|g' % os.path.join(
            mono_lib_dir, 'libgdiplus.so'
        ),
        os.path.join(get_mono_path(), 'etc/mono/config'),
    ])
    subprocess.check_call([
        'sed',
        '-i',
        's|/usr/lib/libMonoPosixHelper.so|%s|g' % os.path.join(
            mono_lib_dir, 'libMonoPosixHelper.so'
        ),
        os.path.join(get_mono_path(), 'etc/mono/config'),
    ])
    return env


def get_mono_path():
    return get_existing_directory_or_raise([
        '/usr/local/share/mono-3.10.0',
        '/tmp/mono',
    ], 'Mono not found')


def lazy_remove_file(filename):
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def ensure_mono(directory, cache_dir):
    if os.path.isdir('/usr/local/share/mono-3.10.0'):
        return
    download_and_unpack(
        get_blobstore_url('/mx-buildpack/mono-3.10.0.tar.gz'),
        directory,
        cache_dir,
    )


def ensure_and_return_java_sdk(mx_version, cache_dir):
    if type(mx_version) is not MXVersion:
        raise Exception('Type should be MXVersion')
    logging.debug('begin download and install java sdk')
    destination = '/tmp/javasdk'
    java_version = get_java_version(mx_version)

    rootfs_java_path = '/usr/lib/jvm/jdk-%s-oracle-x64' % java_version

    if os.path.isdir(rootfs_java_path):
        os.symlink(os.path.join(rootfs_java_path, 'bin/java'), destination)
    else:
        download_and_unpack(
            get_blobstore_url(
                '/mx-buildpack/'
                'oracle-java{java_version}-jdk_{java_version}_amd64.deb'.format(
                    java_version=java_version,
                ),
            ),
            destination,
            cache_dir,
        )
    logging.debug('end download and install java sdk')

    return get_existing_directory_or_raise([
        '/usr/lib/jvm/jdk-%s-oracle-x64' % java_version,
        '/tmp/javasdk/usr/lib/jvm/jdk-%s-oracle-x64' % java_version,
    ], 'Java not found')
