import datetime
import json
import logging
import os
import signal
import socket
import threading
import time
from abc import ABCMeta, abstractmethod
from timeit import default_timer as timer

import psycopg2
import requests
from buildpack import util
from buildpack.core import runtime
from buildpack.infrastructure import database
from lib.m2ee import munin
from lib.m2ee.version import MXVersion
from lib.m2ee.util import strtobool

from . import appdynamics, datadog, dynatrace, newrelic

METRICS_REGISTRIES_KEY = "Metrics.Registries"

# From this MxRuntime version onwards we gather (available) runtime statistics
# from the micrometer library via the telegraf agent
MXVERSION_MICROMETER = MXVersion("9.7.0")


# Handler for user signals
# Initialized from within the start procedure in start.py
def handle_sigusr(_signo, _stack_frame):
    if os.getenv("METRICS_INTERVAL"):  # Only enable if metrics are active
        logging.debug("Handling user signal for metrics...")
        if _signo == signal.SIGUSR1:
            _emit(jvm={"errors": 1.0})
        elif _signo == signal.SIGUSR2:
            _emit(jvm={"ooms": 1.0})


def _emit(**stats):
    stats["version"] = "1.0"
    stats["timestamp"] = datetime.datetime.now().isoformat()
    logging.info("MENDIX-METRICS: %s", json.dumps(stats))


def int_or_default(value, default=0):
    try:
        return int(value)
    except Exception:
        logging.debug("Failed to coerce %s to int.", value, exc_info=True)
        return default


def run(m2ee):
    metrics_interval = os.getenv("METRICS_INTERVAL")
    if metrics_interval:
        if util.is_free_app():
            thread = FreeAppsMetricsEmitterThread(int(metrics_interval), m2ee)
        else:
            thread = PaidAppsMetricsEmitterThread(int(metrics_interval), m2ee)
        thread.daemon = True
        thread.start()
    else:
        logging.info("MENDIX-INTERNAL: Metrics are disabled.")


def get_appmetrics_target():
    return os.getenv("APPMETRICS_TARGET")


def get_micrometer_metrics_url():
    """
    This function is used to provide selection of the trends storage URL.
    There are two options - URL of trends-storage-server (old trends stack),
    or URL of trends-forwarder (new trends stack). This selection is relevant for
    micrometer metrics only. Runtime version 9.7 and above is required.

    """
    use_trends_forwarder = strtobool(os.getenv("USE_TRENDS_FORWARDER", default="true"))

    trends_forwarder_url = os.getenv("TRENDS_FORWARDER_URL", default="")

    if use_trends_forwarder and trends_forwarder_url:
        return trends_forwarder_url
    else:
        return get_metrics_url()


def get_metrics_url():
    return os.getenv("TRENDS_STORAGE_URL")


def _micrometer_runtime_requirement(runtime_version):
    """Check if metrics via micrometer is supported by runtime."""
    # TODO: DISABLE_MICROMETER_METRICS is a temporary flag to disable metrics
    # collection via micrometer till we are ready to do the switchover
    # from admin port metrics to micrometer based metrics
    disable_micrometer = strtobool(os.getenv("DISABLE_MICROMETER_METRICS", "false"))

    runtime_version_supported = runtime_version >= MXVERSION_MICROMETER

    if not disable_micrometer and runtime_version_supported:
        return True

    return False


def micrometer_metrics_enabled(runtime_version):
    """Check for metrics from micrometer."""
    logging.info("checking is micrometer metrics enabled")
    micrometer_enabled=False
    if(_micrometer_runtime_requirement(runtime_version)):
        logging.debug("satisfies micrometer runtime requirement")
        if(bool(get_micrometer_metrics_url())):
            logging.debug("Found micrometer metrics url configured")
            micrometer_enabled = True
        elif(strtobool(os.getenv("NON_MENDIX_PUBLIC_CLOUD","false"))):
            logging.debug("micrometer for non mendix public cloud")
            micrometer_enabled =  True
    return micrometer_enabled
    


def configure_metrics_registry(m2ee):
    """Add custom environment variables to runtime.

    This ensures runtime micrometer sends metrics to telegraf.
    """
    if not micrometer_metrics_enabled(runtime.get_runtime_version()):
        return []

    logging.info("Configuring runtime to push metrics to influx via micrometer")
    if util.is_free_app():
        return [get_freeapps_registry()]

    paidapps_registries = [get_influx_registry()]
    if os.getenv("RUNTIME_LOGIN_METRICS_ENABLED", default=True):
        # Use this toggle to disable runtime user login metrics
        paidapps_registries.append(
            get_influx_registry_with_runtime_login_metrics())

    if (
        datadog.is_enabled()
        or get_appmetrics_target()
        or appdynamics.machine_agent_enabled()
        or dynatrace.is_telegraf_enabled()
        or newrelic.is_enabled()
    ):
        allow_list, deny_list = get_apm_filters()
        paidapps_registries.append(get_statsd_registry(allow_list, deny_list))

    return paidapps_registries


def get_apm_filters():
    if deny_all_apm_metrics():
        allow_list = []
        deny_list = [""]
    else:
        allowed_metrics = os.getenv("APM_METRICS_FILTER_ALLOW")
        denied_metrics = os.getenv("APM_METRICS_FILTER_DENY")

        if allowed_metrics and (denied_metrics is None):
            # if only allowed metrics are specified, deny all the others
            denied_metrics = ""

        allow_list = sanitize_metrics_filter(allowed_metrics)
        deny_list = sanitize_metrics_filter(denied_metrics)

    logging.info(
        "For APM integrations; allowed metric prefixes are: %s, "
        "and denied metric prefixes are: %s",
        allow_list,
        deny_list,
    )

    return allow_list, deny_list


def deny_all_apm_metrics():
    return strtobool(os.getenv("APM_METRICS_FILTER_DENY_ALL", default="false"))


def sanitize_metrics_filter(metric_filter):
    """
    If we use empty string ("") in the filters that we use for statsd registry,
    it accepts/denies every metric since we use type as `nameStartsWith`.
    To prevent breaking the functionality because of this, we need to make sure
    that we pass empty string to the registry filters only if it's intentional.
    So, we strip the leading and trailing commas. Additionally we remove all
    the white spaces to prevent any unintentional mistakes.
    """
    if metric_filter is None:
        return []
    return metric_filter.replace(" ", "").strip(",").split(",")


def get_influx_registry_with_runtime_login_metrics():
    """
    Influx registry definition to publish the runtime user login metrics
    with a higher step-interval to reduce the datapoints
    collected at the telegraf end.
    """
    return {
        "type": "influx",
        "settings": {
            "uri": "http://localhost:8086",
            "db": "mendix",
            "step": "1m",
        },
        "filters": [
            # Login metrics needs to be enabled explicitly as it's disabled
            # by default
            {
                "type": "nameStartsWith",
                "result": "accept",
                "values": ["mx.runtime.user.login"],
            },
            # Filter out all other irrelevant metrics
            {
                "type": "nameStartsWith",
                "result": "deny",
                "values": [""],
            },
        ],
    }


def get_influx_registry():
    # Runtime configuration for influx registry
    # This enables the new stream of metrics coming from micrometer instead
    # of the admin port.
    # https://docs.mendix.com/refguide/metrics#registries-configuration
    # NOTE: Metrics are usually dot separated. But each registry has its
    # own naming format. For instance, a metric like
    # `a.name.like.this` would appear as `a_name_like_this` in
    # influx-formatted metrics output. Hence the filter names uses the
    # dot-separated metric names.
    return {
        "type": "influx",
        "settings": {
            "uri": "http://localhost:8086",
            "db": "mendix",
            "step": "10s",
        },
        "filters": [
            # Filter out irrelevant metrics to reduce
            # the payload size passed to TSS/TFR
            # https://docs.mendix.com/refguide/metrics#filters
            {
                "type": "nameStartsWith",
                "result": "deny",
                "values": ["commons.pool", "jvm.buffer"],
            },
        ],
    }


def get_statsd_registry(allow_list, deny_list):
    return {
        "type": "statsd",
        "settings": {"port": datadog.get_statsd_port()},
        "filters": [
            {
                "type": "nameStartsWith",
                "result": "accept",
                "values": allow_list,
            },
            {
                "type": "nameStartsWith",
                "result": "deny",
                "values": deny_list,
            },
        ],
    }


def get_freeapps_registry():
    # For freeapps we push only the session & login metrics
    return {
        "type": "influx",
        "settings": {
            "uri": "http://localhost:8086",
            "db": "mendix",
            "step": "10s",
        },
        "filters": [
            {
                "type": "nameStartsWith",
                "result": "accept",
                "values": [
                    "mx.runtime.stats.sessions",
                    "mx.runtime.user.login",
                ],
            },
            {"type": "nameStartsWith", "result": "deny", "values": [""]},
        ],
    }


def bypass_loggregator():
    env_var = os.getenv("BYPASS_LOGGREGATOR", "False")
    # Throws a useful message if you put in a nonsensical value.
    # Necessary since we store these in cloud portal as strings.
    try:
        bypass = strtobool(env_var)
    except ValueError:
        logging.warning(
            "Bypass loggregator has a nonsensical value: %s. "
            "Falling back to old loggregator-based metric reporting.",
            env_var,
        )
        return False

    if bypass:
        if os.getenv("TRENDS_STORAGE_URL"):
            return True
        logging.warning(
            "BYPASS_LOGGREGATOR is set to true, but no metrics URL is "
            "set. Falling back to old loggregator-based metric reporting."
        )
        return False
    return False


class MetricsEmitter(metaclass=ABCMeta):
    @abstractmethod
    def emit(self, stats):
        raise NotImplementedError


class LoggingEmitter(MetricsEmitter):
    def emit(self, stats):
        logging.info("MENDIX-METRICS: " + json.dumps(stats))


class MetricsServerEmitter(MetricsEmitter):
    def __init__(self, metrics_url):
        self.metrics_url = metrics_url
        self.fallback_emitter = LoggingEmitter()

    def emit(self, stats):
        try:
            response = requests.post(self.metrics_url, json=stats, timeout=10)
        except Exception:
            logging.debug("Failed to send metrics to trends server.", exc_info=True)
            # Fallback to old pipeline and stdout for now.
            # Later, we will want to buffer and resend.
            # This will be done in DEP-75.
            self.fallback_emitter.emit(stats)
            return

        if response.status_code != 200:
            logging.debug(
                "Failed to send metrics to trends server. Falling back to old "
                "loggregator based method. Got status code %s "
                "for URL %s, with body %s.",
                response.status_code,
                self.metrics_url,
                response.text,
            )

            self.fallback_emitter.emit(stats)


class BaseMetricsEmitterThread(threading.Thread, metaclass=ABCMeta):

    # This base class contains all boilerplate code needed to emit metrics.
    # One must implement in subclass `_select_stats_to_emit` property
    # and `_gather_metrics`.

    def __init__(self, interval, m2ee):
        super().__init__()
        self.interval = interval
        self.m2ee = m2ee
        self.db = None
        self.micrometer_metrics_enabled = micrometer_metrics_enabled(
            runtime.get_runtime_version()
        )

        if bypass_loggregator():
            logging.info("Metrics are logged direct to metrics server.")
            self.emitter = MetricsServerEmitter(metrics_url=get_metrics_url())
        else:
            logging.info("Metrics are logged to stdout.")
            self.emitter = LoggingEmitter()

    @staticmethod
    def _set_stats_info(stats):
        stats["version"] = "1.0"
        stats["timestamp"] = datetime.datetime.now().isoformat()
        stats["instance_index"] = int(os.getenv("CF_INSTANCE_INDEX", "0"))
        return stats

    def emit(self, stats):
        self.emitter.emit(stats)

    @property
    @abstractmethod
    def _select_stats_to_emit(self):
        # This method should return a list of subclass methods.
        # Those methods must return and accept, as a parameter,
        # the 'stats' dictionary.
        # This should be later used in `_gather_metrics` method.
        # :return: [self.func1, self.func2]
        pass

    @abstractmethod
    def _gather_metrics(self):
        # This method should return a dictionary containing all metrics
        # to be emitted.
        # :return: dict

        pass

    def run(self):
        logging.debug("Starting metrics emitter with interval %d", self.interval)
        while True:
            stats = self._gather_metrics()
            stats = self._set_stats_info(stats)
            self.emit(stats)
            time.sleep(self.interval)

    def _inject_health(self, stats):
        health = {}
        translation = {"healthy": 10, "unknown": 7, "sick": 4, "critical": 0}
        stats["health"] = health

        try:
            health_response = self.m2ee.client.check_health()
            if health_response.has_error():
                if (
                    health_response.get_result() == 3
                    and health_response.get_cause() == "java.lang.IllegalArgument"
                    "Exception: Action should not be null"
                ):
                    # Because of an incomplete implementation,
                    # in Mendix 2.5.4 or 2.5.5 this means that the runtime
                    # is health-check capable,
                    # but no health check microflow is defined.
                    health["health"] = translation["unknown"]
                    health["diagnosis"] = "No health check microflow defined"
                elif (
                    health_response.get_result() == health_response.ERR_ACTION_NOT_FOUND
                ):
                    # Admin action 'check_health' does not exist.
                    health["health"] = translation["unknown"]
                    health["diagnosis"] = "No health check microflow defined"
                else:
                    health["health"] = translation["critical"]
                    health["diagnosis"] = (
                        "Health check failed unexpectedly: "
                        f"{health_response.get_error()}"
                    )
            else:
                feedback = health_response.get_feedback()
                health["health"] = translation[feedback["health"]]
                health["diagnosis"] = (
                    feedback["diagnosis"] if "diagnosis" in feedback else ""
                )
                health["response"] = health_response._json
        except Exception as exc:
            logging.warning("Metrics: Failed to get health status %s", str(exc))
            health["health"] = translation["critical"]
            health["diagnosis"] = f"Health check failed unexpectedly: {exc}"
        return stats

    @staticmethod
    def _sanity_check_m2ee_stats(m2ee_stats):
        """Memory usage can never be negative. If this happens, throw a warning
        and ask the customer to contact support, so that we can debug.
        """
        for memory_type, memory_value in m2ee_stats["memory"].items():
            if not isinstance(memory_value, int):
                # Memorypools are here and are stored as a dict
                continue

            if memory_value < 0:
                # memory value can be zero, but not negative
                logging.error(
                    "Memory stats with non-logical values: %s",
                    m2ee_stats["memory"],
                )
                raise RuntimeError(
                    "Memory statistics have non-logical values. This will "
                    "cause incorrect data in your application's metrics. "
                    "Please contact support!"
                )

    def _inject_smap_stats(self, stats):
        smap_stats = {}
        try:
            smap_stats = munin.get_stats_from_smaps(self.m2ee.runner.get_pid())
        except Exception:
            logging.warning("Unable to get stats from smaps file")
        finally:
            if "mendix_runtime" not in stats:
                stats["mendix_runtime"] = {}
            stats["mendix_runtime"]["memory"] = smap_stats
        return stats

    def _inject_m2ee_stats(self, stats):
        try:
            m2ee_stats, java_version = munin.get_stats_from_runtime(
                self.m2ee.client, self.m2ee.config
            )
            if "sessions" in m2ee_stats:
                m2ee_stats["sessions"]["user_sessions"] = {}
            m2ee_stats = munin.augment_and_fix_stats(
                m2ee_stats, self.m2ee.runner.get_pid(), java_version
            )
            self._sanity_check_m2ee_stats(m2ee_stats)
            stats["mendix_runtime"] = m2ee_stats
        except Exception:
            logging.debug("Unable to get metrics from runtime")
        finally:
            return stats

    def _inject_critical_log_stats(self, stats):
        critical_logs_count = 0
        try:
            critical_logs_count = len(self.m2ee.client.get_critical_log_messages())
        except Exception:
            logging.warning("Unable to get critical logs count from runtime")
        finally:
            # Critical logs count has been part of runtime stats from admin
            # port and we continue to fetch that even after the micrometer metrics
            if "mendix_runtime" not in stats:
                stats["mendix_runtime"] = {}
            stats["mendix_runtime"]["critical_logs_count"] = critical_logs_count
        return stats

    def _inject_jvm_failure_metrics(self, stats):

        if "jvm" not in stats:
            stats["jvm"] = {}

        stats["jvm"]["errors"] = 0.0
        stats["jvm"]["ooms"] = 0.0

        return stats

    def _inject_storage_stats(self, stats):
        storage_stats = {}
        runtime_version = runtime.get_runtime_version()
        try:
            storage_stats["get_number_of_files"] = self._get_number_of_files()
        except Exception as exc:
            logging.warning("Metrics: Failed to retrieve number of files, %s", str(exc))
            raise
        if runtime_version >= MXVersion("7.4.0"):
            try:
                storage_stats["get_size_of_files"] = self._get_size_of_files()
            except Exception as exc:
                logging.warning(
                    "Metrics: Failed to retrieve size of files, %s", str(exc)
                )
                raise
        stats["storage"] = storage_stats
        return stats

    def _inject_database_stats(self, stats):
        database_stats = {}
        stats["database"] = database_stats

        try:
            index_size = self._get_database_index_size()
        except psycopg2.OperationalError:
            # For basic apps using Aurora serverless, db connections
            # are closed every day. Handle this db connection error gracefully
            # and need not proceed collecting db stats for this round.
            # https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless.html#aurora-serverless.limitations
            # The database connection will be refreshed in the next round
            # of stats collection.
            logging.warning(
                "Database is currently not reachable. Failed to gather database stats."
            )
            return stats

        if index_size:
            database_stats["indexes_size"] = index_size
        storage = self._get_database_storage()
        if storage:
            database_stats["storage"] = storage
        table_size = self._get_database_table_size()
        if table_size:
            database_stats["tables_size"] = table_size
        mutations_stats = self._get_database_mutations()
        if mutations_stats:
            database_stats.update(mutations_stats)
        tcp_latency = self._get_database_tcp_latency()
        if tcp_latency:
            database_stats["tcp_latency"] = tcp_latency
        return stats

    def _get_database_storage(self):
        if "DATABASE_DISKSTORAGE" in os.environ:
            try:
                return float(os.environ["DATABASE_DISKSTORAGE"])
            except ValueError:
                return None

    def _get_database_tcp_latency(self, timeout: float = 5):
        db_config = database.get_config()
        host, port = self._get_db_host_and_port(db_config["DatabaseHost"])
        # New Socket and Time out
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        # Start a timer
        s_start = timer()

        # Try to Connect
        try:
            sock.connect((host, int(port)))
            sock.shutdown(socket.SHUT_RD)
            sock.close()

        # If something bad happens, the latency is None
        except socket.timeout:
            return None
        except OSError:
            return None

        # Stop Timer
        s_stop = timer()
        s_runtime = "%.2f" % (1000 * (s_stop - s_start))

        return s_runtime

    def _get_database_mutations(self):
        conn = self._get_db_conn()
        db_config = database.get_config()

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT xact_commit, "
                "       xact_rollback, "
                "       tup_inserted, "
                "       tup_updated, "
                "       tup_deleted "
                "FROM pg_stat_database "
                f"WHERE datname = '{db_config['DatabaseName']}';"
            )
            rows = cursor.fetchall()
            return {
                "xact_commit": int_or_default(rows[0][0]),
                "xact_rollback": int_or_default(rows[0][1]),
                "tup_inserted": int_or_default(rows[0][2]),
                "tup_updated": int_or_default(rows[0][3]),
                "tup_deleted": int_or_default(rows[0][4]),
            }
        return None

    def _get_database_table_size(self):
        conn = self._get_db_conn()
        db_config = database.get_config()
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT pg_database_size('{db_config['DatabaseName']}');")
            rows = cursor.fetchall()
            return int_or_default(rows[0][0])

    def _get_database_index_size(self):
        conn = self._get_db_conn()
        with conn.cursor() as cursor:
            cursor.execute(
                """
SELECT SUM(pg_relation_size(quote_ident(indexrelname)::text)) AS index_size
FROM pg_tables t
LEFT OUTER JOIN pg_class c ON t.tablename=c.relname
LEFT OUTER JOIN
  (SELECT c.relname AS ctablename,
          ipg.relname AS indexname,
          x.indnatts AS number_of_columns,
          idx_scan,
          idx_tup_read,
          idx_tup_fetch,
          indexrelname,
          indisunique
   FROM pg_index x
   JOIN pg_class c ON c.oid = x.indrelid
   JOIN pg_class ipg ON ipg.oid = x.indexrelid
   JOIN pg_stat_all_indexes psai ON x.indexrelid = psai.indexrelid)
   AS foo
   ON t.tablename = foo.ctablename
WHERE t.schemaname='public';
"""
            )
            rows = cursor.fetchall()
            return int_or_default(rows[0][0])

    def _get_number_of_files(self):
        conn = self._get_db_conn()

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(id) from system$filedocument WHERE hascontents=true;"  # noqa:C0301
            )
            rows = cursor.fetchall()
            if len(rows) == 0:
                raise Exception("Unexpected result from database query")
            return int_or_default(rows[0][0])

    def _get_size_of_files(self):
        conn = self._get_db_conn()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT SUM(size) from system$filedocument WHERE hascontents=true;"  # noqa:C0301
            )
            rows = cursor.fetchall()
            if len(rows) == 0:
                raise Exception("Unexpected result from database query")
            return int_or_default(rows[0][0])

    def _get_db_conn(self):
        if self.db and self.db.closed != 0:
            self.db.close()
            self.db = None

        if not self.db:
            # get_database config may return None or empty
            db_config = database.get_config()
            if not db_config or "DatabaseType" not in db_config:
                raise ValueError(
                    "Database not set as VCAP or DATABASE_URL. Check "
                    "documentation to see supported configuration options."
                )
            if db_config["DatabaseType"] != "PostgreSQL":
                raise Exception(
                    f"Metrics only supports postgresql, not {db_config['DatabaseType']}"
                )

            host, port = self._get_db_host_and_port(db_config["DatabaseHost"])
            self.db = psycopg2.connect(
                "options='-c statement_timeout=60s'",
                database=db_config["DatabaseName"],
                user=db_config["DatabaseUserName"],
                password=db_config["DatabasePassword"],
                host=host,
                port=port,
                connect_timeout=3,
            )
            self.db.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        return self.db

    @staticmethod
    def _get_db_host_and_port(database_host):
        host_and_port = database_host.split(":")
        host = host_and_port[0]
        if len(host_and_port) > 1:
            port = int(host_and_port[1])
        else:
            port = 5432
        return host, port


class PaidAppsMetricsEmitterThread(BaseMetricsEmitterThread):
    @property
    def _select_stats_to_emit(self):
        selected_stats = []
        if util.is_cluster_leader():
            selected_stats = [
                self._inject_database_stats,
                self._inject_storage_stats,
                self._inject_health,
            ]

        if not self.micrometer_metrics_enabled:
            selected_stats.append(self._inject_m2ee_stats)
        else:
            selected_stats.append(self._inject_smap_stats)
        selected_stats.append(self._inject_critical_log_stats)
        selected_stats.append(self._inject_jvm_failure_metrics)

        return selected_stats

    def _gather_metrics(self):
        stats = {}
        try:
            for inject_method in self._select_stats_to_emit:
                stats = inject_method(stats)
        except psycopg2.OperationalError as exc:
            logging.exception("METRICS: error while gathering metrics")
            stats = {
                "health": {
                    "health": 0,
                    "diagnosis": "Database error: {}".format(str(exc)),
                }
            }
        except Exception:
            logging.exception("METRICS: error while gathering metrics")
            stats = {
                "health": {
                    "health": 4,
                    "diagnosis": "Unable to retrieve metrics",
                }
            }
        finally:
            return stats


class FreeAppsMetricsEmitterThread(BaseMetricsEmitterThread):
    def _get_munin_stats(self):
        m2ee_stats, _ = munin.get_stats_from_runtime(self.m2ee.client, self.m2ee.config)
        return m2ee_stats

    def _inject_user_session_metrics(self, stats):
        session_metrics = {}
        try:
            m2ee_stats = self._get_munin_stats()
            if "sessions" in m2ee_stats:
                m2ee_stats["sessions"]["user_sessions"] = {}
                session_metrics = m2ee_stats["sessions"]
        except Exception:
            logging.debug(
                "METRICS: error while gathering runtime metrics", exc_info=True
            )
        finally:
            # runtime metrics shouldn't be included,
            # but if they were due to some upstream code changes,
            # we would ensure to not override all of them.
            if "mendix_runtime" not in stats:
                stats["mendix_runtime"] = {}
            stats["mendix_runtime"]["sessions"] = session_metrics
            return stats

    @property
    def _select_stats_to_emit(self):
        if not self.micrometer_metrics_enabled:
            return [self._inject_user_session_metrics]
        return []

    def _gather_metrics(self):
        stats = {}
        for inject_method in self._select_stats_to_emit:
            stats = inject_method(stats)
        return stats
