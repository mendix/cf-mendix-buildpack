import datetime
import json
import logging
import os
import socket
import sys
import threading
import time
from abc import ABCMeta, abstractmethod
from timeit import default_timer as timer
from distutils.util import strtobool

import psycopg2
import requests
from buildpack import util
from buildpack.runtime_components import database
from lib.m2ee import munin

BUILDPACK_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(BUILDPACK_DIR, "lib"))


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
        thread.setDaemon(True)
        thread.start()
    else:
        logging.info("MENDIX-INTERNAL: Metrics are disabled.")


def get_metrics_url():
    return os.getenv("TRENDS_STORAGE_URL")


def bypass_loggregator():
    env_var = os.getenv("BYPASS_LOGGREGATOR", "False")
    # Throws a useful message if you put in a nonsensical value.
    # Necessary since we store these in cloud portal as strings.
    try:
        bypass = strtobool(env_var)
    except ValueError as _:
        logging.warning(
            "Bypass loggregator has a nonsensical value: %s. "
            "Falling back to old loggregator-based metric reporting.",
            env_var,
        )
        return False

    if bypass:
        if os.getenv("TRENDS_STORAGE_URL"):
            return True
        else:
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
            logging.debug(
                "Failed to send metrics to trends server.", exc_info=True
            )
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
        stats["instance_index"] = os.getenv("CF_INSTANCE_INDEX", 0)
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
        logging.debug(
            "Starting metrics emitter with interval %d" % self.interval
        )
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
                    and health_response.get_cause()
                    == "java.lang.IllegalArgument"
                    "Exception: Action should not be null"
                ):
                    # Because of an incomplete implementation,
                    # in Mendix 2.5.4 or 2.5.5 this means that the runtime
                    # is health-check capable,
                    # but no health check microflow is defined.
                    health["health"] = translation["unknown"]
                    health["diagnosis"] = "No health check microflow defined"
                elif (
                    health_response.get_result()
                    == health_response.ERR_ACTION_NOT_FOUND
                ):
                    # Admin action 'check_health' does not exist.
                    health["health"] = translation["unknown"]
                    health["diagnosis"] = "No health check microflow defined"
                else:
                    health["health"] = translation["critical"]
                    health["diagnosis"] = (
                        "Health check failed unexpectedly: %s"
                        % health_response.get_error()
                    )
            else:
                feedback = health_response.get_feedback()
                health["health"] = translation[feedback["health"]]
                health["diagnosis"] = (
                    feedback["diagnosis"] if "diagnosis" in feedback else ""
                )
                health["response"] = health_response._json
        except Exception as e:
            logging.warn("Metrics: Failed to get health status, " + str(e))
            health["health"] = translation["critical"]
            health["diagnosis"] = "Health check failed unexpectedly: %s" % e
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

            critical_logs_count = len(
                self.m2ee.client.get_critical_log_messages()
            )
            m2ee_stats["critical_logs_count"] = critical_logs_count
            self._sanity_check_m2ee_stats(m2ee_stats)
            stats["mendix_runtime"] = m2ee_stats
        except Exception:
            logging.debug("Unable to get metrics from runtime")
        finally:
            return stats

    def _inject_storage_stats(self, stats):
        storage_stats = {}
        try:
            storage_stats["get_number_of_files"] = self._get_number_of_files()
        except Exception as e:
            logging.warn(
                "Metrics: Failed to retrieve number of files, " + str(e)
            )
            raise
        stats["storage"] = storage_stats
        return stats

    def _inject_database_stats(self, stats):
        database_stats = {}
        index_size = self._get_database_index_size()
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
        stats["database"] = database_stats
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
                "WHERE datname = '%s';" % (db_config["DatabaseName"],)
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
            cursor.execute(
                "SELECT pg_database_size('%s');" % (db_config["DatabaseName"],)
            )
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
                "SELECT COUNT(id) from system$filedocument WHERE hascontents=true;"  # noqa:E501
            )
            rows = cursor.fetchall()
            if len(rows) == 0:
                raise Exception("Unexpected result from database query")
            return int_or_default(rows[0][0])

    def _get_size_of_files(self):
        conn = self._get_db_conn()
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "SELECT sum(size) from system$filedocument WHERE hascontents=true;"  # noqa:E501
                )
                rows = cursor.fetchall()
                if len(rows) == 0:
                    return 0
                return int_or_default(rows[0][0])
            except Exception:
                # We ignore errors here, as the information is
                # not available for older mendix versions
                logging.debug(
                    "METRICS: Error retrieving file sizes", exc_info=True
                )
                return 0

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
                    "Metrics only supports postgresql, not %s"
                    % db_config["DatabaseType"]
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
            self.db.set_isolation_level(
                psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT
            )
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
        if util.i_am_primary_instance():
            selected_stats = [
                self._inject_database_stats,
                self._inject_storage_stats,
                self._inject_health,
            ]
        selected_stats.append(self._inject_m2ee_stats)
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
        m2ee_stats, _ = munin.get_stats_from_runtime(
            self.m2ee.client, self.m2ee.config
        )
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
        return [self._inject_user_session_metrics]

    def _gather_metrics(self):
        stats = {}
        for inject_method in self._select_stats_to_emit:
            stats = inject_method(stats)
        return stats
