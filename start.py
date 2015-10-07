#!/usr/bin/env python
import json
import os
import re
import signal
import subprocess
import time
import sys
sys.path.insert(0, 'lib')
import buildpackutil
from m2ee import M2EE, logger
import logging

logger.setLevel(logging.INFO)

logger.info('Started Mendix Cloud Foundry Buildpack')


def pre_process_m2ee_yaml():
    runtime_port = int(os.environ['PORT'])

    subprocess.check_call([
        'sed',
        '-i',
        's|BUILD_PATH|%s|g; s|RUNTIME_PORT|%d|; s|ADMIN_PORT|%d|'
        % (os.getcwd(), runtime_port, runtime_port + 1),
        '.local/m2ee.yaml'
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
    prefs_template = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE map SYSTEM "http://java.sun.com/dtd/preferences.dtd">
<map MAP_XML_VERSION="1.0">
  <entry key="id" value="{{SERVER_ID}}"/>
  <entry key="license_key" value="{{LICENSE_KEY}}"/>
</map>"""

    license = os.environ.get('LICENSE_KEY', None)
    server_id = os.environ.get('SERVER_ID', None)
    if license is not None and server_id is not None:
        logger.debug('A license was supplied so going to activate it')
        prefs_body = prefs_template.replace(
            '{{SERVER_ID}}', server_id
            ).replace(
            '{{LICENSE_KEY}}', license
            )
        prefs_dir = os.path.expanduser('~/../.java/.userPrefs/com/mendix/core')
        if not os.path.isdir(prefs_dir):
            os.makedirs(prefs_dir)
        with open(os.path.join(prefs_dir, 'prefs.xml'), 'w') as prefs_file:
            prefs_file.write(prefs_body)


def get_scheduled_events(metadata):
    scheduled_events = os.getenv('SCHEDULED_EVENTS', None)
    if scheduled_events is None or scheduled_events == 'ALL':
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
    for constant in metadata['Constants']:
        env = 'MX_%s' % constant['Name'].replace('.', '_')
        value = os.environ.get(env)
        if value is None:
            value = constant['DefaultValue']
            logger.debug(
                'constant not found in environment, taking default '
                'value %s' % constant['Name']
            )
        if constant['Type'] == 'Integer':
            value = int(value)
        constants[constant['Name']] = value
    return constants


def set_heap_size(javaopts):
    max_memory = os.environ.get('MEMORY_LIMIT', '512m').upper()
    match = re.search('([0-9]+)([A-Z])', max_memory)
    max_memory = '%d%s' % (int(match.group(1)) / 2, match.group(2))
    heap_size = os.environ.get('HEAP_SIZE', max_memory)
    javaopts.append('-Xmx%s' % heap_size)
    javaopts.append('-Xms%s' % heap_size)
    logger.debug('Java heap size set to %s' % max_memory)


def get_filestore_config(m2ee):
    access_key = secret = bucket = encryption_keys = key_suffix = None

    vcap_services = buildpackutil.get_vcap_services_data()
    if vcap_services and 'amazon-s3' in vcap_services:
        _conf = vcap_services['amazon-s3'][0]['credentials']
        access_key = _conf['access_key_id']
        secret = _conf['secret_access_key']
        bucket = _conf['bucket']
        if 'encryption_keys' in _conf:
            encryption_keys = _conf['encryption_keys']
        if 'key_suffix' in _conf:
            key_suffix = _conf['key_suffix']

    access_key = os.getenv('S3_ACCESS_KEY_ID', access_key)
    secret = os.getenv('S3_SECRET_ACCESS_KEY', secret)
    bucket = os.getenv('S3_BUCKET_NAME', bucket)
    if 'S3_ENCRYPTION_KEYS' in os.environ:
        encryption_keys = json.loads(os.getenv('S3_ENCRYPTION_KEYS'))

    perform_deletes = os.getenv('S3_PERFORM_DELETES', '').lower() == 'false'
    key_suffix = os.getenv('S3_KEY_SUFFIX', key_suffix)
    endpoint = os.getenv('S3_ENDPOINT')
    v2_auth = os.getenv('S3_USE_V2_AUTH', '').lower() == 'true'

    if not (access_key and secret and bucket):
        logger.warning(
            'External file store not configured, uploaded files in the app '
            'will not persist across restarts. See https://github.com/mendix/'
            'cf-mendix-buildpack for file store configuration details.'
        )
        return {}

    logger.info(
        'S3 config detected, activating external file store'
    )
    config = {
        'com.mendix.core.StorageService': 'com.mendix.storage.s3',
        'com.mendix.storage.s3.AccessKeyId': access_key,
        'com.mendix.storage.s3.SecretAccessKey': secret,
        'com.mendix.storage.s3.BucketName': bucket,
    }
    if not perform_deletes:
        config['com.mendix.storage.s3.PerformDeleteFromStorage'] = False
    if key_suffix:
        config['com.mendix.storage.s3.ResourceNameSuffix'] = key_suffix
    if v2_auth:
        config['com.mendix.storage.s3.UseV2Auth'] = v2_auth
    if endpoint:
        config['com.mendix.storage.s3.EndPoint'] = endpoint
    if m2ee.config.get_runtime_version() >= 5.17 and encryption_keys:
        config['com.mendix.storage.s3.EncryptionKeys'] = encryption_keys
    return config


def determine_cluster_redis_credentials():
    vcap_services = buildpackutil.get_vcap_services_data()
    if vcap_services and 'rediscloud' in vcap_services:
          return vcap_services['rediscloud'][0]['credentials']
    logger.error("Redis Cloud Service should be configured for this app")
    sys.exit(1)


def is_cluster_enabled():
    os.getenv('CLUSTER_ENABLED', 'false') == 'true'

def get_cluster_config():
    config = {}
    if is_cluster_enabled():
        config['com.mendix.core.IsClustered'] = 'true'
        config['com.mendix.core.state.implementation'] = (
            os.getenv('CLUSTER_STATE_IMPLEMENTATION', 'mxdb')
        )

        if config['com.mendix.core.state.implementation'].startswith('redis'):
            redis_creds = determine_cluster_redis_credentials()
            max_conns = os.getenv('CLUSTER_STATE_REDIS_MAX_CONNECTIONS', '30')

            config.update({
                'com.mendix.core.state.redis.host': redis_creds['hostname'],
                'com.mendix.core.state.redis.port': redis_creds['port'],
                'com.mendix.core.state.redis.secret': redis_creds['password'],
                'com.mendix.core.state.redis.maxconnections': max_conns,
            })
    return config


def get_custom_settings(metadata, existing_config):
    custom_settings_key = 'Configuration'
    if custom_settings_key in metadata:
        config = {}
        for k, v in metadata[custom_settings_key].iteritems():
            if k not in existing_config:
                config[k] = v
        return config
    else:
        return {}


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

    if (m2ee.config.get_runtime_version() >= 5.15 and 
          os.getenv('DISABLE_STICKY_SESSIONS', '').lower() != 'true' and 
          not is_cluster_enabled()):
        app_config['com.mendix.core.SessionIdCookieName'] = 'JSESSIONID'

    mxruntime_config.update(app_config)
    mxruntime_config.update(buildpackutil.get_database_config(
        development_mode=is_development_mode(),
    ))
    mxruntime_config.update(get_filestore_config(m2ee))
    mxruntime_config.update(get_cluster_config())
    mxruntime_config.update(get_custom_settings(metadata, mxruntime_config))
    for k, v in os.environ.iteritems():
        if k.startswith('MXRUNTIME_'):
            mxruntime_config[
                k.replace('MXRUNTIME_', '', 1).replace('_', '.')
            ] = v


def set_application_name(m2ee, name):
    logger.debug('Application name is %s' % name)
    m2ee.config._conf['m2ee']['app_name'] = name


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
    set_runtime_config(
        m2ee.config._model_metadata,
        m2ee.config._conf['mxruntime'],
        vcap_data,
        m2ee,
    )
    set_heap_size(m2ee.config._conf['m2ee']['javaopts'])
    activate_new_relic(m2ee, vcap_data['application_name'])
    set_application_name(m2ee, vcap_data['application_name'])
    return m2ee


def set_up_logging_file():
    os.mkfifo('log/out.log')
    subprocess.Popen([
        'sed',
        '--unbuffered',
        's|^[0-9\-]\+\s[0-9:\.]\+\s||',
        'log/out.log',
    ])


def start_app(m2ee):
    m2ee.start_appcontainer()
    if not m2ee.send_runtime_config():
        sys.exit(1)

    logger.debug('Appcontainer has been started')

    abort = False
    success = False
    while not (success or abort):
        startresponse = m2ee.client.start({'autocreatedb': True})
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
                m2eeresponse = m2ee.client.execute_ddl_commands()
                m2eeresponse.display_error()
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
    logger.debug('Creating admin user')
    m2eeresponse = m2ee.client.create_admin_user({
        'password': os.environ.get('ADMIN_PASSWORD'),
    })
    if m2eeresponse.has_error():
        m2eeresponse.display_error()
        sys.exit(1)

    logger.debug('Setting admin user password')
    m2eeresponse = m2ee.client.create_admin_user({
        'username': m2ee.config._model_metadata['AdminUser'],
        'password': os.environ.get('ADMIN_PASSWORD'),
    })
    if m2eeresponse.has_error():
        m2eeresponse.display_error()
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


def display_running_version(m2ee):
    if m2ee.config.get_runtime_version() >= 4.4:
        feedback = m2ee.client.about().get_feedback()
        if 'model_version' in feedback:
            logger.info('Model version: %s' % feedback['model_version'])


def loop_until_process_dies(m2ee):
    while m2ee.runner.check_pid():
        time.sleep(10)
    logger.info('process died, stopping')
    sys.exit(1)


if __name__ == '__main__':
    pre_process_m2ee_yaml()
    activate_license()
    set_up_logging_file()
    m2ee = set_up_m2ee_client(get_vcap_data())

    def sigterm_handler(_signo, _stack_frame):
        m2ee.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, sigterm_handler)

    start_app(m2ee)
    create_admin_user(m2ee)
    display_running_version(m2ee)
    configure_debugger(m2ee)
    loop_until_process_dies(m2ee)
