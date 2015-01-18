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

logger.setLevel(10)

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
    logger.info('Java heap size set to %s' % max_memory)


def set_runtime_config(metadata, mxruntime_config, vcap_data):
    database_config = buildpackutil.get_database_config()
    application_config = {
        'ApplicationRootUrl': 'https://%s' % vcap_data['application_uris'][0],
        'MicroflowConstants': get_constants(metadata),
    }
    runtime_config = dict(database_config.items() + application_config.items())

    for key, value in runtime_config.iteritems():
        mxruntime_config[key] = value


def set_application_name(m2ee, name):
    logger.debug('Application name is %s' % name)
    m2ee.config._conf['m2ee']['app_name'] = name


def activate_new_relic(m2ee, app_name):
    if os.environ.get('NEW_RELIC_LICENSE_KEY') is None:
        logger.debug(
            'Skipping New Relic setup, no license key found in environment'
        )
        return
    logger.info('Adding new relic')
    m2ee_section = m2ee.config._conf['m2ee']
    if 'custom_environment' not in m2ee_section:
        m2ee_section['custom_environment'] = {}
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
    )
    set_heap_size(m2ee.config._conf['m2ee']['javaopts'])
    activate_new_relic(m2ee, vcap_data['application_name'])
    set_application_name(m2ee, vcap_data['application_name'])
    return m2ee


def set_up_logging_file():
    os.mkfifo('log/out.log')
    subprocess.Popen(['cat', 'log/out.log'])


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
    logger.info('Creating admin user')
    m2eeresponse = m2ee.client.create_admin_user({
        'password': os.environ.get('ADMIN_PASSWORD'),
    })
    if m2eeresponse.has_error():
        m2eeresponse.display_error()
        sys.exit(1)

    logger.info('Setting admin user password')
    m2eeresponse = m2ee.client.create_admin_user({
        'username': m2ee.config._model_metadata['AdminUser'],
        'password': os.environ.get('ADMIN_PASSWORD'),
    })
    if m2eeresponse.has_error():
        m2eeresponse.display_error()
        sys.exit(1)


def display_running_version(m2ee):
    feedback = m2ee.client.about().get_feedback()
    logger.info("Using %s version %s" % (feedback['name'], feedback['version']))
    if m2ee.config.get_runtime_version() >= 4.4:
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
    loop_until_process_dies(m2ee)
