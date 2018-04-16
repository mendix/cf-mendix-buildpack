import os
import yaml
import subprocess
import buildpackutil


def is_enabled():
    return os.getenv('DD_API_KEY') is not None


def _get_hostname():
    domain = buildpackutil.get_vcap_data()['application_uris'][0].split('/')[0]
    return domain + '-' + os.getenv('CF_INSTANCE_INDEX', '')


def update_config(m2ee, app_name):
    if not is_enabled():
        return
    m2ee.config._conf['m2ee']['javaopts'].extend([
        '-Dcom.sun.management.jmxremote',
        '-Dcom.sun.management.jmxremote.port=7845',
        '-Dcom.sun.management.jmxremote.local.only=true',
        '-Dcom.sun.management.jmxremote.authenticate=false',
        '-Dcom.sun.management.jmxremote.ssl=false',
        '-Djava.rmi.server.hostname=127.0.0.1',
    ])
    m2ee.config._conf['logging'].append({
        'type': 'file',
        'name': 'FileSubscriberDataDog',
        'autosubscribe': 'INFO',
        'filename': os.path.join(os.getcwd(), 'log', 'datadog.log'),
        'max_size': 1048576,
        'max_rotation': 1,
    })
# disable until mendix version has been released
#    jar = os.path.abspath('.local/datadog/mx-agent-assembly-0.1-SNAPSHOT.jar')
#    m2ee.config._conf['m2ee']['javaopts'].extend([
#        '-javaagent:{}'.format(jar),
#        '-Xbootclasspath/a:{}'.format(jar),
#    ])
    subprocess.check_call(('mkdir', '-p', '.local/datadog'))
    with open('.local/datadog/datadog.yaml', 'w') as fh:
        config = {
            'dd_url': 'https://app.datadoghq.com',
            'api_key': None,  # set via DD_API_KEY instead
            'confd_path': '.local/datadog/conf.d',
            'logs_enabled': True,
            'log_file': '/dev/null',
            'hostname': _get_hostname(),
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
        fh.write(yaml.dump(config))
    subprocess.check_call(('mkdir', '-p', '.local/datadog/conf.d/mendix.d'))
    subprocess.check_call(('mkdir', '-p', '.local/datadog/run'))
    with open('.local/datadog/conf.d/mendix.d/conf.yaml', 'w') as fh:
        config = {
            'logs': [{
                'type': 'file',
                'path': 'log/datadog.log',
                'service': _get_hostname(),
                'source': 'mendix',
                'sourcecategory': 'sourcecode',
                'tags': 'env:prod',
            }],
        }
        fh.write(yaml.dump(config))
    subprocess.check_call(('mkdir', '-p', '.local/datadog/conf.d/jmx.d'))
    with open('.local/datadog/conf.d/jmx.d/conf.yaml', 'w') as fh:
        config = {
            'init_config': {
                'collect_default_metrics': True,
                'is_jmx': True,
            },
            'instances': [{
                'host': 'localhost',
                'port': 7845,
                'java_bin_path': '.local/bin/java',
            }],
        }
        fh.write(yaml.dump(config))


def compile(install_path, cache_dir):
    if not is_enabled():
        return
    buildpackutil.download_and_unpack(
        buildpackutil.get_blobstore_url(
            '/mx-buildpack/experimental/dd-v0.6.tar.gz',
        ),
        os.path.join(install_path, 'datadog'),
        cache_dir=cache_dir,
    )


def run():
    if not is_enabled():
        return
    subprocess.Popen(('.local/datadog/dd-agent', '-c', '.local/datadog', 'start'))
    e = dict(os.environ)
    e['DD_HOSTNAME'] = _get_hostname()
    subprocess.Popen(('.local/datadog/dd-process-agent', '-logtostderr', '-config', '.local/datadog/datadog.yaml'), env=e)
