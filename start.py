#!/usr/bin/env python
import json
import os
import re
import signal
import subprocess
import time
import sys
import base64
import uuid
sys.path.insert(0, 'lib')
import requests
from m2ee import M2EE, logger
import buildpackutil
import logging
import instadeploy
import metrics
from nginx import get_path_config, gen_htpasswd
from buildpackutil import i_am_primary_instance

logger.setLevel(buildpackutil.get_buildpack_loglevel())

logger.info('Started Mendix Cloud Foundry Buildpack v1.2.2')

logging.getLogger('m2ee').propagate = False


app_is_restarting = False
default_m2ee_password = str(uuid.uuid4()).replace('-', '@') + 'A1'


def get_nginx_port():
    return int(os.environ['PORT'])


def get_runtime_port():
    return get_nginx_port() + 1


def get_admin_port():
    return get_nginx_port() + 2


def get_deploy_port():
    return get_nginx_port() + 3


def pre_process_m2ee_yaml():
    subprocess.check_call([
        'sed',
        '-i',
        's|BUILD_PATH|%s|g; s|RUNTIME_PORT|%d|; s|ADMIN_PORT|%d|; s|ADMIN_PASSWORD|%s|'
        % (os.getcwd(), get_runtime_port(), get_admin_port(), get_m2ee_password()),
        '.local/m2ee.yaml'
    ])


def use_instadeploy(mx_version):
    return mx_version >= 6.7 or str(mx_version) == '6-build10037'


def get_admin_password():
    return os.getenv('ADMIN_PASSWORD')


def get_m2ee_password():
    m2ee_password = os.getenv('M2EE_PASSWORD', get_admin_password())
    if not m2ee_password:
        logger.warning('No M2EE_PASSWORD set, generating a random password for protection')
        m2ee_password = default_m2ee_password
    return m2ee_password


def set_up_nginx_files(m2ee):
    lines = ''
    x_frame_options = os.environ.get('X_FRAME_OPTIONS', 'ALLOW')
    if x_frame_options == 'ALLOW':
        x_frame_options = ''
    else:
        x_frame_options = "add_header X-Frame-Options '%s';" % x_frame_options
    if use_instadeploy(m2ee.config.get_runtime_version()):
        mxbuild_upstream = 'proxy_pass http://mendix_mxbuild'
    else:
        mxbuild_upstream = 'return 501'
    with open('nginx/conf/nginx.conf') as fh:
        lines = ''.join(fh.readlines())
    lines = lines.replace(
        'CONFIG', get_path_config()
    ).replace(
        'NGINX_PORT', str(get_nginx_port())
    ).replace(
        'RUNTIME_PORT', str(get_runtime_port())
    ).replace(
        'ADMIN_PORT', str(get_admin_port())
    ).replace(
        'DEPLOY_PORT', str(get_deploy_port())
    ).replace(
        'ROOT', os.getcwd()
    ).replace(
        'XFRAMEOPTIONS', x_frame_options
    ).replace(
        'MXBUILD_UPSTREAM', mxbuild_upstream
    )
    for line in lines.split('\n'):
        logger.debug(line)
    with open('nginx/conf/nginx.conf', 'w') as fh:
        fh.write(lines)

    gen_htpasswd({'MxAdmin': get_m2ee_password()})
    gen_htpasswd(
        {'deploy': os.getenv('DEPLOY_PASSWORD')},
        file_name_suffix='-mxbuild'
    )

    buildpackutil.mkdir_p('nginx/logs')
    subprocess.check_call(['touch', 'nginx/logs/access.log'])
    subprocess.check_call(['touch', 'nginx/logs/error.log'])


def start_nginx():
    subprocess.Popen([
        'nginx/sbin/nginx', '-p', 'nginx', '-c', 'conf/nginx.conf'
    ])
    subprocess.Popen([
        'tail', '-f', 'nginx/logs/error.log'
    ])


def get_vcap_data():
    if os.environ.get('VCAP_APPLICATION'):
        return json.loads(os.environ.get('VCAP_APPLICATION'))
    else:
        return {
            'application_uris': ['example.com'],
            'application_name': 'My App',
        }


def activate_license():
    prefs_dir = os.path.expanduser('~/../.java/.userPrefs/com/mendix/core')
    buildpackutil.mkdir_p(prefs_dir)

    prefs_template = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE map SYSTEM "http://java.sun.com/dtd/preferences.dtd">
<map MAP_XML_VERSION="1.0">
  <entry key="id" value="{{LICENSE_ID}}"/>
  <entry key="license_key" value="{{LICENSE_KEY}}"/>
</map>"""

    license_key = os.environ.get(
        'FORCED_LICENSE_KEY',
        os.environ.get('LICENSE_KEY', None)
    )
    server_id = os.environ.get(
        'FORCED_SERVER_ID',
        os.environ.get('SERVER_ID', None)
    )
    license_id = os.environ.get(
        'FORCED_LICENSE_ID',
        os.environ.get('LICENSE_ID', None)
    )
    if server_id:
        logger.warning('SERVER_ID is deprecated, please use LICENSE_ID instead')

    if not license_id:
        license_id = server_id

    if license_key is not None and license_id is not None:
        logger.debug('A license was supplied so going to activate it')
        prefs_body = prefs_template.replace(
            '{{LICENSE_ID}}', license_id
            ).replace(
            '{{LICENSE_KEY}}', license_key
            )
        with open(os.path.join(prefs_dir, 'prefs.xml'), 'w') as prefs_file:
            prefs_file.write(prefs_body)


def get_scheduled_events(metadata):
    scheduled_events = os.getenv('SCHEDULED_EVENTS', None)
    if not i_am_primary_instance():
        logger.debug(
            'Disabling all scheduled events because I am not the primary '
            'instance'
        )
        return ('NONE', None)
    elif scheduled_events is None or scheduled_events == 'ALL':
        logger.debug('Enabling all scheduled events')
        return ('ALL', None)
    elif scheduled_events == 'NONE':
        logger.debug('Disabling all scheduled events')
        return ('NONE', None)
    else:
        parsed_scheduled_events = scheduled_events.split(',')
        metadata_scheduled_events = [
            scheduled_event['Name']
            for scheduled_event
            in metadata['ScheduledEvents']
        ]
        result = []
        for scheduled_event in parsed_scheduled_events:
            if scheduled_event not in metadata_scheduled_events:
                logger.warning(
                    'Scheduled event defined but not detected in model: "%s"'
                    % scheduled_event
                )
            else:
                result.append(scheduled_events)
        logger.debug('Enabling scheduled events %s' % ','.join(result))
        return ('SPECIFIED', result)


def get_constants(metadata):
    constants = {}

    constants_from_json = {}
    constants_json = os.environ.get(
        'CONSTANTS',
        json.dumps(constants_from_json)
    )
    try:
        constants_from_json = json.loads(constants_json)
    except Exception as e:
        logger.warning('Failed to parse CONSTANTS: ' + str(e))

    for constant in metadata['Constants']:
        constant_name = constant['Name']
        env_name = 'MX_%s' % constant_name.replace('.', '_')
        value = os.environ.get(
            env_name,
            constants_from_json.get(constant_name)
        )
        if value is None:
            value = constant['DefaultValue']
            logger.debug(
                'Constant not found in environment, taking default '
                'value %s' % constant_name
            )
        if constant['Type'] == 'Integer':
            value = int(value)
        constants[constant_name] = value
    return constants


def set_heap_size(javaopts, vcap_max_mem):
    max_memory = os.environ.get('MEMORY_LIMIT')
    env_heap_size = os.environ.get('HEAP_SIZE')

    if max_memory:
        match = re.search('([0-9]+)([A-Z])', max_memory.upper())
        heap_size = '%d%s' % (int(match.group(1)) / 2, match.group(2))
    else:
        heap_size = str(int(vcap_max_mem) / 2) + 'M'

    if env_heap_size:
        max_memory = max_memory[:-1] if max_memory else vcap_max_mem
        heap_size = env_heap_size if int(env_heap_size[:-1]) < int(max_memory) else heap_size

    javaopts.append('-Xmx%s' % heap_size)
    javaopts.append('-Xms%s' % heap_size)
    logger.debug('Java heap size set to %s' % heap_size)


def _get_s3_specific_config(vcap_services, m2ee):
    access_key = secret = bucket = encryption_keys = key_suffix = None
    endpoint = None
    v2_auth = ''

    if 'amazon-s3' in vcap_services:
        _conf = vcap_services['amazon-s3'][0]['credentials']
        access_key = _conf['access_key_id']
        secret = _conf['secret_access_key']
        bucket = _conf['bucket']
        if 'encryption_keys' in _conf:
            encryption_keys = _conf['encryption_keys']
        if 'key_suffix' in _conf:
            key_suffix = _conf['key_suffix']
        if 'endpoint' in _conf:
            endpoint = _conf['endpoint']

    elif 'p-riakcs' in vcap_services:
        _conf = vcap_services['p-riakcs'][0]['credentials']
        access_key = _conf['access_key_id']
        secret = _conf['secret_access_key']
        pattern = r'https://(([^:]+):([^@]+)@)?([^/]+)/(.*)'
        match = re.search(pattern, _conf['uri'])
        endpoint = 'https://' + match.group(4)
        bucket = match.group(5)
        v2_auth = 'true'

    access_key = os.getenv('S3_ACCESS_KEY_ID', access_key)
    secret = os.getenv('S3_SECRET_ACCESS_KEY', secret)
    bucket = os.getenv('S3_BUCKET_NAME', bucket)
    if 'S3_ENCRYPTION_KEYS' in os.environ:
        encryption_keys = json.loads(os.getenv('S3_ENCRYPTION_KEYS'))

    dont_perform_deletes = os.getenv('S3_PERFORM_DELETES', 'true').lower() == 'false'
    key_suffix = os.getenv('S3_KEY_SUFFIX', key_suffix)
    endpoint = os.getenv('S3_ENDPOINT', endpoint)
    v2_auth = os.getenv('S3_USE_V2_AUTH', v2_auth).lower() == 'true'
    sse = os.getenv('S3_USE_SSE', '').lower() == 'true'

    if not (access_key and secret and bucket):
        return None

    logger.info(
        'S3 config detected, activating external file store'
    )
    config = {
        'com.mendix.core.StorageService': 'com.mendix.storage.s3',
        'com.mendix.storage.s3.AccessKeyId': access_key,
        'com.mendix.storage.s3.SecretAccessKey': secret,
        'com.mendix.storage.s3.BucketName': bucket,
    }

    if dont_perform_deletes:
        logger.debug('disabling perform deletes for runtime')
        config['com.mendix.storage.s3.PerformDeleteFromStorage'] = False
    if key_suffix:
        config['com.mendix.storage.s3.ResourceNameSuffix'] = key_suffix
    if v2_auth:
        config['com.mendix.storage.s3.UseV2Auth'] = v2_auth
    if endpoint:
        config['com.mendix.storage.s3.EndPoint'] = endpoint
    if m2ee.config.get_runtime_version() >= 5.17 and encryption_keys:
        config['com.mendix.storage.s3.EncryptionKeys'] = encryption_keys
    if m2ee.config.get_runtime_version() >= 6 and sse:
        config['com.mendix.storage.s3.UseSSE'] = sse
    return config


def _get_swift_specific_config(vcap_services, m2ee):
    if 'Object-Storage' not in vcap_services:
        return None

    if m2ee.config.get_runtime_version() < 6.7:
        logger.warning('Can not configure Object Storage with Mendix < 6.7')
        return None

    creds = vcap_services['Object-Storage'][0]['credentials']

    container_name = os.getenv('SWIFT_CONTAINER_NAME', 'mendix')

    return {
        'com.mendix.core.StorageService': 'com.mendix.storage.swift',
        'com.mendix.storage.swift.Container': container_name,
        'com.mendix.storage.swift.Container.AutoCreate': True,
        'com.mendix.storage.swift.credentials.DomainId': creds['domainId'],
        'com.mendix.storage.swift.credentials.Authurl': creds['auth_url'],
        'com.mendix.storage.swift.credentials.Username': creds['username'],
        'com.mendix.storage.swift.credentials.Password': creds['password'],
        'com.mendix.storage.swift.credentials.Region': creds['region'],
    }


def _get_azure_storage_specific_config(vcap_services, m2ee):
    if 'azure-storage' not in vcap_services:
        return None

    if m2ee.config.get_runtime_version() < 6.7:
        logger.warning('Can not configure Azure Storage with Mendix < 6.7')
        return None

    creds = vcap_services['azure-storage'][0]['credentials']

    container_name = os.getenv('AZURE_CONTAINER_NAME', 'mendix')

    return {
        'com.mendix.core.StorageService': 'com.mendix.storage.azure',
        'com.mendix.storage.azure.Container': container_name,
        'com.mendix.storage.azure.AccountName': creds['storage_account_name'],
        'com.mendix.storage.azure.AccountKey': creds['primary_access_key'],
    }


def get_filestore_config(m2ee):
    vcap_services = buildpackutil.get_vcap_services_data()

    config = _get_s3_specific_config(vcap_services, m2ee)

    if config is None:
        config = _get_swift_specific_config(vcap_services, m2ee)

    if config is None:
        config = _get_azure_storage_specific_config(vcap_services, m2ee)

    if config is None:
        logger.warning(
            'External file store not configured, uploaded files in the app '
            'will not persist across restarts. See https://github.com/mendix/'
            'cf-mendix-buildpack for file store configuration details.'
        )
        return {}
    else:
        return config


def get_certificate_authorities():
    config = {}
    cas = os.getenv('CERTIFICATE_AUTHORITIES', None)
    if cas:
        ca_list = cas.split('-----BEGIN CERTIFICATE-----')
        n = 0
        files = []
        for ca in ca_list:
            if '-----END CERTIFICATE-----' in ca:
                ca = '-----BEGIN CERTIFICATE-----' + ca
                location = os.path.abspath(
                    '.local/certificate_authorities.%d.crt' % n
                )
                with open(location, 'w') as output_file:
                    output_file.write(cas)
                files.append(location)
                n += 1
        config['CACertificates'] = ','.join(files)
        buildpackutil.mkdir_p(os.path.join(os.getcwd(), 'model', 'resources'))
    return config


def get_client_certificates():
    config = {}
    client_certificates_json = os.getenv('CLIENT_CERTIFICATES', '[]')
    '''
    [
        {
        'pfx': 'base64...', # required
        'password': '',
        'pin_to': ['Module.WS1', 'Module2.WS2'] # optional
        },
        {...}
    ]
    '''
    client_certificates = json.loads(client_certificates_json)
    num = 0
    files = []
    passwords = []
    pins = {}
    for client_certificate in client_certificates:
        pfx = base64.b64decode(client_certificate['pfx'])
        location = os.path.abspath(
            '.local/client_certificate.%d.crt' % num
        )
        with open(location, 'w') as f:
            f.write(pfx)
        passwords.append(client_certificate['password'])
        files.append(location)
        if 'pin_to' in client_certificate:
            for ws in client_certificate['pin_to']:
                pins[ws] = location
        num += 1
    if len(files) > 0:
        config['ClientCertificates'] = ','.join(files)
        config['ClientCertificatePasswords'] = ','.join(passwords)
        config['WebServiceClientCertificates'] = pins
    return config


def get_custom_settings(metadata, existing_config):
    if os.getenv('USE_DATA_SNAPSHOT', 'false').lower() == 'true':
        custom_settings_key = 'Configuration'
        if custom_settings_key in metadata:
            config = {}
            for k, v in metadata[custom_settings_key].iteritems():
                if k not in existing_config:
                    config[k] = v
            return config
    return {}


def get_custom_runtime_settings():
    custom_runtime_settings = {}
    custom_runtime_settings_json = os.environ.get(
        'CUSTOM_RUNTIME_SETTINGS',
        json.dumps(custom_runtime_settings)
    )
    try:
        custom_runtime_settings = json.loads(custom_runtime_settings_json)
    except Exception as e:
        logger.warning('Failed to parse CUSTOM_RUNTIME_SETTINGS: ' + str(e))

    for k, v in os.environ.iteritems():
        if k.startswith('MXRUNTIME_'):
            custom_runtime_settings[
                k.replace('MXRUNTIME_', '', 1).replace('_', '.')
            ] = v

    return custom_runtime_settings


def is_development_mode():
    return os.getenv('DEVELOPMENT_MODE', '').lower() == 'true'


def set_runtime_config(metadata, mxruntime_config, vcap_data, m2ee):
    scheduled_event_execution, my_scheduled_events = (
        get_scheduled_events(metadata)
    )
    app_config = {
        'ApplicationRootUrl': 'https://%s' % vcap_data['application_uris'][0],
        'MicroflowConstants': get_constants(metadata),
        'ScheduledEventExecution': scheduled_event_execution,
    }

    if my_scheduled_events is not None:
        app_config['MyScheduledEvents'] = my_scheduled_events

    if is_development_mode():
        logger.warning(
            'Runtime is being started in Development Mode. Set '
            'DEVELOPMENT_MODE to "false" (currently "true") to '
            'set it to production.'
        )
        app_config['DTAPMode'] = 'D'

    if (m2ee.config.get_runtime_version() >= 7 and
            not i_am_primary_instance()):
        app_config['com.mendix.core.isClusterSlave'] = 'true'
    elif (m2ee.config.get_runtime_version() >= 5.15 and
            os.getenv('ENABLE_STICKY_SESSIONS', 'false').lower() == 'true'):
        logger.info('Enabling sticky sessions')
        app_config['com.mendix.core.SessionIdCookieName'] = 'JSESSIONID'

    mxruntime_config.update(app_config)
    mxruntime_config.update(buildpackutil.get_database_config(
        development_mode=is_development_mode(),
    ))
    mxruntime_config.update(get_filestore_config(m2ee))
    mxruntime_config.update(get_certificate_authorities())
    mxruntime_config.update(get_client_certificates())
    mxruntime_config.update(get_custom_settings(metadata, mxruntime_config))
    mxruntime_config.update(get_custom_runtime_settings())


def set_application_name(m2ee, name):
    logger.debug('Application name is %s' % name)
    m2ee.config._conf['m2ee']['app_name'] = name


def activate_appdynamics(m2ee, app_name):
    if not buildpackutil.appdynamics_used():
        return
    logger.info('Adding app dynamics')
    m2ee.config._conf['m2ee']['javaopts'].append(
        '-javaagent:{path}'.format(
            path=os.path.abspath('.local/ver4.1.7.1/javaagent.jar')
        )
    )
    APPDYNAMICS_AGENT_NODE_NAME = 'APPDYNAMICS_AGENT_NODE_NAME'
    if os.getenv(APPDYNAMICS_AGENT_NODE_NAME):
        m2ee.config._conf['m2ee']['custom_environment'][
            APPDYNAMICS_AGENT_NODE_NAME
        ] = (
            '%s-%s' % (
                os.getenv(APPDYNAMICS_AGENT_NODE_NAME),
                os.getenv('CF_INSTANCE_INDEX', '0'),
            )
        )


def activate_new_relic(m2ee, app_name):
    if buildpackutil.get_new_relic_license_key() is None:
        logger.debug(
            'Skipping New Relic setup, no license key found in environment'
        )
        return
    logger.info('Adding new relic')
    m2ee_section = m2ee.config._conf['m2ee']
    if 'custom_environment' not in m2ee_section:
        m2ee_section['custom_environment'] = {}
    m2ee_section['custom_environment']['NEW_RELIC_LICENSE_KEY'] = (
        buildpackutil.get_new_relic_license_key()
    )
    m2ee_section['custom_environment']['NEW_RELIC_APP_NAME'] = app_name
    m2ee_section['custom_environment']['NEW_RELIC_LOG'] = (
        os.path.abspath('newrelic/agent.log')
    )

    m2ee.config._conf['m2ee']['javaopts'].append(
        '-javaagent:{path}'.format(
            path=os.path.abspath('newrelic/newrelic.jar')
        )
    )


def set_up_m2ee_client(vcap_data):
    m2ee = M2EE(yamlfiles=['.local/m2ee.yaml'], load_default_files=False)
    version = m2ee.config.get_runtime_version()

    mendix_runtimes_path = '/usr/local/share/mendix-runtimes.git'
    mendix_runtime_version_path = os.path.join(os.getcwd(), 'runtimes', str(version))
    if os.path.isdir(mendix_runtimes_path) and not os.path.isdir(mendix_runtime_version_path):
        buildpackutil.mkdir_p(mendix_runtime_version_path)
        env = dict(os.environ)
        env['GIT_WORK_TREE'] = mendix_runtime_version_path

        # checkout the runtime version
        process = subprocess.Popen(['git', 'checkout', str(version), '-f'], cwd=mendix_runtimes_path, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process.communicate()
        if process.returncode != 0:
            # do a 'git fetch --tags' to refresh the bare repo, then retry to checkout the runtime version
            logger.info('mendix runtime version {mx_version} is missing in this rootfs'.format(mx_version=version))
            process = subprocess.Popen(['git', 'fetch', '--tags', '&&', 'git', 'checkout', str(version), '-f'],
                                       cwd=mendix_runtimes_path, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            process.communicate()
            if process.returncode != 0:
                # download the mendix runtime version from our blobstore
                logger.info('unable to use rootfs for mendix runtime version {mx_version}'.format(mx_version=version))
                url = buildpackutil.get_blobstore_url('/runtime/mendix-%s.tar.gz' % str(version))
                buildpackutil.download_and_unpack(url, os.path.join(os.getcwd(), 'runtimes'))

        m2ee.reload_config()
    set_runtime_config(
        m2ee.config._model_metadata,
        m2ee.config._conf['mxruntime'],
        vcap_data,
        m2ee,
    )
    set_heap_size(m2ee.config._conf['m2ee']['javaopts'],
                  vcap_data['limits']['mem'])
    activate_new_relic(m2ee, vcap_data['application_name'])
    activate_appdynamics(m2ee, vcap_data['application_name'])
    set_application_name(m2ee, vcap_data['application_name'])
    java_version = buildpackutil.get_java_version(
        m2ee.config.get_runtime_version()
    )
    java_opts = m2ee.config._conf['m2ee']['javaopts']
    if java_version.startswith('7'):
        java_opts.append('-XX:MaxPermSize=128M')
    elif java_version.startswith('8'):
        java_opts.append('-XX:MaxMetaspaceSize=128M')
    return m2ee


def set_up_logging_file():
    buildpackutil.lazy_remove_file('log/out.log')
    os.mkfifo('log/out.log')
    subprocess.Popen([
        'sed',
        '--unbuffered',
        's|^[0-9\-]\+\s[0-9:\.]\+\s||',
        'log/out.log',
    ])


def service_backups():
    vcap_services = buildpackutil.get_vcap_services_data()
    if not vcap_services or 'schnapps' not in vcap_services:
        logger.debug("No backup service detected")
        return

    backup_service = {}
    if 'amazon-s3' in vcap_services:
        s3_credentials = vcap_services['amazon-s3'][0]['credentials']
        backup_service['filesCredentials'] = {
            'accessKey': s3_credentials['access_key_id'],
            'secretKey': s3_credentials['secret_access_key'],
            'bucketName': s3_credentials['bucket'],
        }
        if 'key_suffix' in s3_credentials:  # Not all s3 plans have this field
            backup_service['filesCredentials']['keySuffix'] = s3_credentials['key_suffix']

    try:
        db_config = buildpackutil.get_database_config()
        if db_config['DatabaseType'] != 'PostgreSQL':
            raise Exception(
                'Schnapps only supports postgresql, not %s'
                % db_config['DatabaseType']
            )
        host_and_port = db_config['DatabaseHost'].split(':')
        backup_service['databaseCredentials'] = {
            'host': host_and_port[0],
            'username': db_config['DatabaseUserName'],
            'password': db_config['DatabasePassword'],
            'dbname': db_config['DatabaseName'],
            'port': int(host_and_port[1]) if len(host_and_port) > 1 else 5432,
        }
    except Exception as e:
        logger.exception(
            'Schnapps will not be activated because error occurred with '
            'parsing the database credentials'
        )
        return
    schnapps_url = vcap_services['schnapps'][0]['credentials']['url']
    schnapps_api_key = vcap_services['schnapps'][0]['credentials']['apiKey']

    try:
        result = requests.put(
            schnapps_url,
            headers={
                'Content-Type': 'application/json',
                'apiKey': schnapps_api_key
            },
            data=json.dumps(backup_service),
        )
    except Exception as e:
        logger.warning('Failed to contact backup service: ' + e)
        return

    if result.status_code == 200:
        logger.info("Successfully updated backup service")
    else:
        logger.warning("Failed to update backup service: " + result.text)


def start_app(m2ee):
    m2ee.start_appcontainer()
    if not m2ee.send_runtime_config():
        sys.exit(1)

    logger.debug('Appcontainer has been started')

    abort = False
    success = False
    while not (success or abort):
        startresponse = m2ee.client.start({'autocreatedb': True})
        logger.debug('startresponse received')
        result = startresponse.get_result()
        if result == 0:
            success = True
            logger.info('The MxRuntime is fully started now.')
        else:
            startresponse.display_error()
            if result == 2:
                logger.warning('DB does not exists')
                abort = True
            elif result == 3:
                if i_am_primary_instance():
                    if os.getenv('SHOW_DDL_COMMANDS', '').lower() == 'true':
                        for line in m2ee.client.get_ddl_commands({
                            "verbose": True
                        }).get_feedback()['ddl_commands']:
                            logger.info(line)
                    m2eeresponse = m2ee.client.execute_ddl_commands()
                    if m2eeresponse.has_error():
                        logger.info(m2eeresponse.get_error())
                else:
                    logger.info(
                        'waiting 10 seconds before primary instance '
                        'synchronizes database'
                    )
                    time.sleep(10)
            elif result == 4:
                logger.warning('Not enough constants!')
                abort = True
            elif result == 5:
                logger.warning('Unsafe password!')
                abort = True
            elif result == 6:
                logger.warning('Invalid state!')
                abort = True
            elif result == 7 or result == 8 or result == 9:
                logger.warning(
                    "You'll have to fix the configuration and run start "
                    "again... (or ask for help..)"
                )
                abort = True
            else:
                abort = True
    if abort:
        logger.warning('start failed, stopping')
        sys.exit(1)


def create_admin_user(m2ee):
    logger.info('Ensuring admin user credentials')
    app_admin_password = get_admin_password()
    if os.getenv('M2EE_PASSWORD'):
        logger.debug('M2EE_PASSWORD is set so skipping creation of application admin password')
        return
    if not app_admin_password:
        logger.warning('ADMIN_PASSWORD not set, so skipping creation of application admin password')
        return
    logger.debug('Creating admin user')

    m2eeresponse = m2ee.client.create_admin_user({
        'password': app_admin_password
    })
    if m2eeresponse.has_error():
        m2eeresponse.display_error()
        if not is_development_mode():
            sys.exit(1)

    logger.debug('Setting admin user password')
    m2eeresponse = m2ee.client.create_admin_user({
        'username': m2ee.config._model_metadata['AdminUser'],
        'password': app_admin_password
    })
    if m2eeresponse.has_error():
        m2eeresponse.display_error()
        if not is_development_mode():
            sys.exit(1)


def configure_debugger(m2ee):
    debugger_password = os.environ.get('DEBUGGER_PASSWORD')

    if debugger_password is None:
        logger.debug('Not configuring debugger, as environment variable '
                     'was not found')
        return

    response = m2ee.client.enable_debugger({
        'password': debugger_password
    })
    response.display_error()
    if not response.has_error():
        logger.info(
            'The remote debugger is now enabled, the password to '
            'use is %s' % debugger_password
        )
        logger.info(
            'You can use the remote debugger option in the Mendix '
            'Business Modeler to connect to the /debugger/ sub '
            'url on your application (e.g. '
            'https://app.example.com/debugger/). '
        )


def _transform_logging(nodes):
    res = []
    for k, v in nodes.iteritems():
        res.append({
            "name": k,
            "level": v
        })
    return res


def configure_logging(m2ee):
    for k, v in os.environ.iteritems():
        if k.startswith('LOGGING_CONFIG'):
            m2ee.set_log_levels(
                '*',
                nodes=_transform_logging(
                    json.loads(v)
                ),
                force=True,
            )


def display_running_version(m2ee):
    if m2ee.config.get_runtime_version() >= 4.4:
        feedback = m2ee.client.about().get_feedback()
        if 'model_version' in feedback:
            logger.info('Model version: %s' % feedback['model_version'])


def loop_until_process_dies(m2ee):
    while True:
        if app_is_restarting or m2ee.runner.check_pid():
            time.sleep(10)
        else:
            break
    logger.info('process died, stopping')
    sys.exit(1)


def set_up_instadeploy_if_deploy_password_is_set(m2ee):
    if os.getenv('DEPLOY_PASSWORD'):
        mx_version = m2ee.config.get_runtime_version()
        if use_instadeploy(mx_version):
            def reload_callback():
                m2ee.client.request('reload_model')

            def restart_callback():
                global app_is_restarting
                app_is_restarting = True
                if not m2ee.stop():
                    m2ee.terminate()
                complete_start_procedure_safe_to_use_for_restart(m2ee)
                app_is_restarting = False

            instadeploy.InstaDeployThread(
                get_deploy_port(),
                restart_callback,
                reload_callback,
                mx_version,
            ).start()
        else:
            logger.warning(
                'Not setting up InstaDeploy because this mendix '
                'runtime version %s does not support it' % mx_version
            )


def start_metrics(m2ee):
    metrics_interval = os.getenv('METRICS_INTERVAL')
    if metrics_interval:
        metrics.MetricsEmitterThread(int(metrics_interval), m2ee).start()


def complete_start_procedure_safe_to_use_for_restart(m2ee):
    buildpackutil.mkdir_p('model/lib/userlib')
    set_up_logging_file()
    start_app(m2ee)
    create_admin_user(m2ee)
    configure_logging(m2ee)
    display_running_version(m2ee)
    configure_debugger(m2ee)


if __name__ == '__main__':
    if os.getenv('CF_INSTANCE_INDEX') is None:
        logger.warning(
            'CF_INSTANCE_INDEX environment variable not found. Assuming '
            'responsibility for scheduled events execution and database '
            'synchronization commands.'
        )
    pre_process_m2ee_yaml()
    activate_license()
    m2ee = set_up_m2ee_client(get_vcap_data())

    def sigterm_handler(_signo, _stack_frame):
        m2ee.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, sigterm_handler)

    service_backups()
    set_up_nginx_files(m2ee)
    complete_start_procedure_safe_to_use_for_restart(m2ee)
    set_up_instadeploy_if_deploy_password_is_set(m2ee)
    start_metrics(m2ee)
    start_nginx()
    loop_until_process_dies(m2ee)
