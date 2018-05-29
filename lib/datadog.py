import os
import json
import yaml
import subprocess
import buildpackutil


def _get_api_key():
    return os.getenv('DD_API_KEY')


def _get_tags():
    return json.loads(
        os.getenv('DD_TAGS', '[]')
    )


def is_enabled():
    return _get_api_key() is not None


def _get_hostname():
    dd_hostname = os.environ.get('DD_HOSTNAME')
    if dd_hostname is None:
        domain = buildpackutil.get_vcap_data()['application_uris'][0].split('/')[0]
        dd_hostname = domain + '-' + os.getenv('CF_INSTANCE_INDEX', '')
    return dd_hostname


def _get_service():
    dd_service = os.environ.get('DD_SERVICE')
    if dd_service is None:
        dd_service = _get_hostname()
    return dd_service


def update_config(m2ee, app_name):
    if not is_enabled():
        return
    tags = _get_tags()
    m2ee.config._conf['m2ee']['javaopts'].extend([
        '-Dcom.sun.management.jmxremote',
        '-Dcom.sun.management.jmxremote.port=7845',
        '-Dcom.sun.management.jmxremote.local.only=true',
        '-Dcom.sun.management.jmxremote.authenticate=false',
        '-Dcom.sun.management.jmxremote.ssl=false',
        '-Djava.rmi.server.hostname=127.0.0.1',
    ])
    if m2ee.config.get_runtime_version() >= 7.15:
        m2ee.config._conf['logging'].append({
            'type': 'tcpjsonlines',
            'name': 'DataDogSubscriber',
            'autosubscribe': 'INFO',
            'host': 'localhost',
            'port': 9032,
        })
    if m2ee.config.get_runtime_version() >= 7.14:
        jar = os.path.abspath('.local/datadog/mx-agent-assembly-0.1-SNAPSHOT.jar')
        m2ee.config._conf['m2ee']['javaopts'].extend([
            '-javaagent:{}'.format(jar),
            '-Xbootclasspath/a:{}'.format(jar),
        ])
        # if not explicitly set, default to statsd
        m2ee.config._conf['mxruntime'].setdefault(
            'com.mendix.metrics.Type', 'statsd'
        )
    subprocess.check_call(('mkdir', '-p', '.local/datadog'))
    with open('.local/datadog/datadog.yaml', 'w') as fh:
        config = {
            'dd_url': 'https://app.datadoghq.com',
            'api_key': None,  # set via DD_API_KEY instead
            'confd_path': '.local/datadog/conf.d',
            'logs_enabled': True,
            'log_file': '/dev/null',  # will be printed via stdout/stderr
            'hostname': _get_hostname(),
            'tags': tags,
            'process_config': {
                'enabled': 'true',  # has to be string
                'log_file': '/dev/null',
            },
            'apm_config': {
                'enabled': True,
                'max_traces_per_second': 10,
            },
            'logs_config': {
                'run_path': '.local/datadog/run',
            },
        }
        fh.write(yaml.safe_dump(config))
    subprocess.check_call(('mkdir', '-p', '.local/datadog/conf.d/mendix.d'))
    subprocess.check_call(('mkdir', '-p', '.local/datadog/run'))
    with open('.local/datadog/conf.d/mendix.d/conf.yaml', 'w') as fh:
        config = {
            'logs': [{
                'type': 'tcp',
                'port': '9032',
                'service': _get_service(),
                'source': 'mendix',
                'tags': tags,
            }],
        }
        fh.write(yaml.safe_dump(config))
    subprocess.check_call(('mkdir', '-p', '.local/datadog/conf.d/jmx.d'))
    with open('.local/datadog/conf.d/jmx.d/conf.yaml', 'w') as fh:
        # jmx beans and values can be inspected with jmxterm
        # download the jmxterm jar into the container
        # and run app/.local/bin/java -jar ~/jmxterm.jar
        #
        # the extra attributes are only available from Mendix 7.15.0+
        config = {
            'init_config': {
                'collect_default_metrics': True,
                'is_jmx': True,
            },
            'instances': [{
                'host': 'localhost',
                'port': 7845,
                'java_bin_path': '.local/bin/java',
                'java_options': '-Xmx50m -Xms5m',
                'conf': [{
                    'include': {
                        'bean': 'com.mendix:type=SessionInformation',
                        # NamedUsers = 1;
                        # NamedUserSessions = 0;
                        # AnonymousSessions = 0;

                        'attribute': {
                            'NamedUsers': {'metrics_type': 'gauge'},
                            'NamedUserSessions': {'metrics_type': 'gauge'},
                            'AnonymousSessions': {'metrics_type': 'gauge'},
                        },
                    },
                }, {
                    'include': {
                        'bean': 'com.mendix:type=Statistics,name=DataStorage',
                        # Selects = 1153;
                        # Inserts = 1;
                        # Updates = 24;
                        # Deletes = 0;
                        # Transactions = 25;

                        'attribute': {
                            'Selects': {'metrics_type': 'counter'},
                            'Updates': {'metrics_type': 'counter'},
                            'Inserts': {'metrics_type': 'counter'},
                            'Deletes': {'metrics_type': 'counter'},
                            'Transactions': {'metrics_type': 'counter'},
                        },
                    },
                }, {
                    'include': {
                        'bean': 'com.mendix:type=General',
                        # Languages = en_US;
                        # Entities = 24;

                        'attribute': {
                            'Entities': {'metrics_type': 'gauge'},
                        },
                    },
                }, {
                    'include': {
                        'bean': 'com.mendix:type=JettyThreadPool',
                        # Threads = 8
                        # IdleThreads = 3;
                        # IdleTimeout = 60000;
                        # MaxThreads = 254;
                        # StopTimeout = 30000;
                        # MinThreads = 8;
                        # ThreadsPriority = 5;
                        # QueueSize = 0;

                        'attribute': {
                            'Threads': {'metrics_type': 'gauge'},
                            'MaxThreads': {'metrics_type': 'gauge'},
                            'IdleThreads': {'metrics_type': 'gauge'},
                            'QueueSize': {'metrics_type': 'gauge'},
                        },
                    },
                }],
                #  }, {
                #    'include': {
                #        'bean': 'com.mendix:type=Jetty',
                #        # ConnectedEndPoints = 0;
                #        # IdleTimeout = 30000;
                #        # RequestsActiveMax = 0;

                #        'attribute': {
                #        }
                #    },
            }],
        }
        fh.write(yaml.safe_dump(config))

    _set_up_postgres()


def _set_up_postgres():
    if not buildpackutil.i_am_primary_instance():
        return
    dbconfig = buildpackutil.get_database_config()
    for k in (
        'DatabaseType',
        'DatabaseUserName',
        'DatabasePassword',
        'DatabaseHost',
    ):
        if k not in dbconfig:
            return
    if dbconfig['DatabaseType'] != 'PostgreSQL':
        return
    with open('.local/datadog/conf.d/postgres.yaml', 'w') as fh:
        config = {
            'init_config': {
            },
            'instances': [{
                'host': dbconfig['DatabaseHost'].split(':')[0],
                'port': int(dbconfig['DatabaseHost'].split(':')[1]),
                'username': dbconfig['DatabaseUserName'],
                'password': dbconfig['DatabasePassword'],
                'dbname': dbconfig['DatabaseName'],
            }],
        }
        fh.write(yaml.safe_dump(config))


def compile(install_path, cache_dir):
    if not is_enabled():
        return
    buildpackutil.download_and_unpack(
        buildpackutil.get_blobstore_url(
            '/mx-buildpack/experimental/dd-v0.7.3.tar.gz',
        ),
        os.path.join(install_path, 'datadog'),
        cache_dir=cache_dir,
    )


def run():
    if not is_enabled():
        return
    e = dict(os.environ)
    e['DD_HOSTNAME'] = _get_hostname()
    e['DD_API_KEY'] = _get_api_key()
    e['LD_LIBRARY_PATH'] = os.path.abspath('.local/datadog/lib/')
    subprocess.Popen((
        '.local/datadog/dd-agent', '-c', '.local/datadog', 'start',
    ), env=e)
    subprocess.Popen((
        '.local/datadog/dd-process-agent', '-logtostderr',
        '-config', '.local/datadog/datadog.yaml',
    ), env=e)
