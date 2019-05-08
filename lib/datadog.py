import os
import json
import yaml
import subprocess
import buildpackutil
import database_config
from m2ee import logger

DD_SIDECAR = "dd-v0.10.0.tar.gz"
MX_AGENT_JAR = "mx-agent-v0.10.1.jar"


logger.setLevel(buildpackutil.get_buildpack_loglevel())


def get_api_key():
    return os.getenv("DD_API_KEY")


def is_enabled():
    return get_api_key() is not None


def _is_installed():
    return os.path.exists(".local/datadog/datadog-agent")


def _get_service():
    dd_service = os.environ.get("DD_SERVICE")
    if dd_service is None:
        dd_service = buildpackutil.get_hostname()
    return dd_service


def enable_runtime_agent(m2ee):
    # check already configured
    if 0 in [
        v.find("-javaagent") for v in m2ee.config._conf["m2ee"]["javaopts"]
    ]:
        return

    if m2ee.config.get_runtime_version() >= 7.14:
        # This is a dirty way to make it self-service until we pick up DEP-59.
        # After DEP-59 we can pick this up from a dedicated env var.
        agent_config = ""
        if "MetricsAgentConfig" in m2ee.config._conf["mxruntime"]:
            v = m2ee.config._conf["mxruntime"]["MetricsAgentConfig"]
            try:
                json.loads(v)  # ensure that this contains valid json
                config_file_path = os.path.abspath(
                    ".local/MetricsAgentConfig.json"
                )
                with open(config_file_path, "w") as fh:
                    fh.write(v)
                agent_config = "=config=" + config_file_path
            except ValueError:
                logger.error(
                    "Could not parse json from MetricsAgentConfig",
                    exc_info=True,
                )
        jar = os.path.abspath(".local/datadog/{}".format(MX_AGENT_JAR))
        m2ee.config._conf["m2ee"]["javaopts"].extend(
            [
                "-javaagent:{}{}".format(jar, agent_config),
                "-Xbootclasspath/a:{}".format(jar),
            ]
        )
        # if not explicitly set, default to statsd
        m2ee.config._conf["mxruntime"].setdefault(
            "com.mendix.metrics.Type", "statsd"
        )


def update_config(m2ee, app_name):
    if not is_enabled() or not _is_installed():
        return

    tags = buildpackutil.get_tags()
    if buildpackutil.is_appmetrics_enabled():
        statsd_port = 8126
    else:
        statsd_port = 8125
    m2ee.config._conf["m2ee"]["javaopts"].extend(
        [
            "-Dcom.sun.management.jmxremote",
            "-Dcom.sun.management.jmxremote.port=7845",
            "-Dcom.sun.management.jmxremote.local.only=true",
            "-Dcom.sun.management.jmxremote.authenticate=false",
            "-Dcom.sun.management.jmxremote.ssl=false",
            "-Djava.rmi.server.hostname=127.0.0.1",
        ]
    )
    if m2ee.config.get_runtime_version() >= 7.15:
        m2ee.config._conf["logging"].append(
            {
                "type": "tcpjsonlines",
                "name": "DataDogSubscriber",
                "autosubscribe": "INFO",
                "host": "localhost",
                # For MX8 integer is supported again, this change needs to be
                # made when MX8 is GA
                "port": "9032",
            }
        )
    enable_runtime_agent(m2ee)
    subprocess.check_call(("mkdir", "-p", ".local/datadog"))
    with open(".local/datadog/datadog.yaml", "w") as fh:
        config = {
            "dd_url": "https://app.datadoghq.com",
            "api_key": None,  # set via DD_API_KEY instead
            "confd_path": ".local/datadog/conf.d",
            "logs_enabled": True,
            "log_file": "/dev/null",  # will be printed via stdout/stderr
            "hostname": buildpackutil.get_hostname(),
            "tags": tags,
            "process_config": {
                "enabled": "true",  # has to be string
                "log_file": "/dev/null",
            },
            "apm_config": {"enabled": True, "max_traces_per_second": 10},
            "logs_config": {"run_path": ".local/datadog/run"},
            "use_dogstatsd": True,
            "dogstatsd_port": statsd_port,
        }
        fh.write(yaml.safe_dump(config))
    subprocess.check_call(("mkdir", "-p", ".local/datadog/conf.d/mendix.d"))
    subprocess.check_call(("mkdir", "-p", ".local/datadog/run"))
    with open(".local/datadog/conf.d/mendix.d/conf.yaml", "w") as fh:
        config = {
            "logs": [
                {
                    "type": "tcp",
                    "port": "9032",
                    "service": _get_service(),
                    "source": "mendix",
                    "tags": tags,
                }
            ]
        }
        fh.write(yaml.safe_dump(config))
    subprocess.check_call(("mkdir", "-p", ".local/datadog/conf.d/jmx.d"))
    with open(".local/datadog/conf.d/jmx.d/conf.yaml", "w") as fh:
        # jmx beans and values can be inspected with jmxterm
        # download the jmxterm jar into the container
        # and run app/.local/bin/java -jar ~/jmxterm.jar
        #
        # the extra attributes are only available from Mendix 7.15.0+
        config = {
            "init_config": {"collect_default_metrics": True, "is_jmx": True},
            "instances": [
                {
                    "host": "localhost",
                    "port": 7845,
                    "java_bin_path": ".local/bin/java",
                    "java_options": "-Xmx50m -Xms5m",
                    "reporter": "statsd:localhost:{}".format(statsd_port),
                    # 'refresh_beans': 10, # runtime takes time to initialize the beans
                    "conf": [
                        {
                            "include": {
                                "bean": "com.mendix:type=SessionInformation",
                                # NamedUsers = 1;
                                # NamedUserSessions = 0;
                                # AnonymousSessions = 0;
                                "attribute": {
                                    "NamedUsers": {"metrics_type": "gauge"},
                                    "NamedUserSessions": {
                                        "metrics_type": "gauge"
                                    },
                                    "AnonymousSessions": {
                                        "metrics_type": "gauge"
                                    },
                                },
                            }
                        },
                        {
                            "include": {
                                "bean": "com.mendix:type=Statistics,name=DataStorage",
                                # Selects = 1153;
                                # Inserts = 1;
                                # Updates = 24;
                                # Deletes = 0;
                                # Transactions = 25;
                                "attribute": {
                                    "Selects": {"metrics_type": "counter"},
                                    "Updates": {"metrics_type": "counter"},
                                    "Inserts": {"metrics_type": "counter"},
                                    "Deletes": {"metrics_type": "counter"},
                                    "Transactions": {
                                        "metrics_type": "counter"
                                    },
                                },
                            }
                        },
                        {
                            "include": {
                                "bean": "com.mendix:type=General",
                                # Languages = en_US;
                                # Entities = 24;
                                "attribute": {
                                    "Entities": {"metrics_type": "gauge"}
                                },
                            }
                        },
                        {
                            "include": {
                                "bean": "com.mendix:type=JettyThreadPool",
                                # Threads = 8
                                # IdleThreads = 3;
                                # IdleTimeout = 60000;
                                # MaxThreads = 254;
                                # StopTimeout = 30000;
                                # MinThreads = 8;
                                # ThreadsPriority = 5;
                                # QueueSize = 0;
                                "attribute": {
                                    "Threads": {"metrics_type": "gauge"},
                                    "MaxThreads": {"metrics_type": "gauge"},
                                    "IdleThreads": {"metrics_type": "gauge"},
                                    "QueueSize": {"metrics_type": "gauge"},
                                },
                            }
                        },
                    ],
                    #  }, {
                    #    'include': {
                    #        'bean': 'com.mendix:type=Jetty',
                    #        # ConnectedEndPoints = 0;
                    #        # IdleTimeout = 30000;
                    #        # RequestsActiveMax = 0;
                    #        'attribute': {
                    #        }
                    #    },
                }
            ],
        }
        fh.write(yaml.safe_dump(config))

    _set_up_postgres()


def _set_up_postgres():
    # TODO: set up a way to disable this, on shared database (mxapps.io) we
    # don't want to allow this.
    if not buildpackutil.i_am_primary_instance():
        return
    dbconfig = database_config.get_database_config()
    for k in (
        "DatabaseType",
        "DatabaseUserName",
        "DatabasePassword",
        "DatabaseHost",
    ):
        if k not in dbconfig:
            return
    if dbconfig["DatabaseType"] != "PostgreSQL":
        return
    with open(".local/datadog/conf.d/postgres.yaml", "w") as fh:
        config = {
            "init_config": {},
            "instances": [
                {
                    "host": dbconfig["DatabaseHost"].split(":")[0],
                    "port": int(dbconfig["DatabaseHost"].split(":")[1]),
                    "username": dbconfig["DatabaseUserName"],
                    "password": dbconfig["DatabasePassword"],
                    "dbname": dbconfig["DatabaseName"],
                }
            ],
        }
        fh.write(yaml.safe_dump(config))


def download(install_path, cache_dir):
    # the dd-vX.Y.Z.tar.gz needs to be created manually
    #
    # see all bundled resources here:
    # curl -s https://cdn.mendix.com/mx-buildpack/experimental/dd-vX.Y.Z.tar.gz | tar tzv
    #
    # mx-agent-x.x.x.jar is generated by the Mendix Runtime team
    #
    # the rest is copied from the datadog-agent debian package
    # install datadog-agent in a ubuntu-16.04 docker image
    # and extract the required python / dd-agent / jmxfetch dependencies
    #
    # lib/libpython2.7.so.1.0 is necessary so the go agent can include a cpython interpreter
    #
    # create the package with:
    # tar zcvf ../dd-vX.Y.Z.tar.gz --owner 0 --group 0 *
    # aws s3 cp ../dd-vX.Y.Z.tar.gz s3://mx-cdn/mx-buildpack/experimental/
    buildpackutil.download_and_unpack(
        buildpackutil.get_blobstore_url(
            "/mx-buildpack/experimental/{}".format(DD_SIDECAR)
        ),
        os.path.join(install_path, "datadog"),
        cache_dir=cache_dir,
    )


def compile(install_path, cache_dir):
    if not is_enabled():
        return

    download(install_path, cache_dir)


def run():
    if not is_enabled():
        return

    if not _is_installed():
        logger.warn(
            "DataDog agent isn"
            "t installed yet but DD_API_KEY is set. "
            + "Please push or restage your app to complete DataDog installation."
        )
        return

    e = dict(os.environ)
    e["DD_HOSTNAME"] = buildpackutil.get_hostname()
    e["DD_API_KEY"] = get_api_key()
    e["LD_LIBRARY_PATH"] = os.path.abspath(".local/datadog/lib/")
    subprocess.Popen(
        (".local/datadog/datadog-agent", "-c", ".local/datadog", "start"),
        env=e,
    )
    # after datadog agent 6.3 is released, a separate process agent might
    # not be necessary any more: https://github.com/DataDog/datadog-process-agent/pull/124
    subprocess.Popen(
        (
            ".local/datadog/process-agent",
            "-logtostderr",
            "-config",
            ".local/datadog/datadog.yaml",
        ),
        env=e,
    )
