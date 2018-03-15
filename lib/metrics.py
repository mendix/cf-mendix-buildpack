import os
import sys
import json
import time
from m2ee import logger, munin

import threading
import datetime

BUILDPACK_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

sys.path.insert(0, os.path.join(BUILDPACK_DIR, 'lib'))
import buildpackutil
import psycopg2


class MetricsEmitterThread(threading.Thread):

    def __init__(self, interval, m2ee):
        super(MetricsEmitterThread, self).__init__()
        self.interval = interval
        self.m2ee = m2ee
        self.db = None

    def run(self):
        logger.debug(
            'Starting metrics emitter with interval %d' % self.interval
        )
        while True:

            try:
                stats = {
                    'version': '1.0',
                    'timestamp': datetime.datetime.now().isoformat(),
                }
                stats = self._inject_m2ee_stats(stats)
                if buildpackutil.i_am_primary_instance():
                    stats = self._inject_storage_stats(stats)
                    stats = self._inject_database_stats(stats)
                    stats = self._inject_health(stats)
                logger.info('MENDIX-METRICS: ' + json.dumps(stats))
            except Exception as e:
                logger.exception('METRICS: error while gathering metrics')

            time.sleep(self.interval)

    def _inject_health(self, stats):
        health = {}
        translation = {'healthy': 10,
                       'unknown': 7,
                       'sick': 3,
                       'critical': 0}
        stats['health'] = health

        try:
            health_response = self.m2ee.client.check_health()
            if health_response.has_error():
                if (health_response.get_result() == 3 and
                        health_response.get_cause() == "java.lang.IllegalArgument"
                        "Exception: Action should not be null"):
                    # Because of an incomplete implementation, in Mendix 2.5.4 or
                    # 2.5.5 this means that the runtime is health-check
                    # capable, but no health check microflow is defined.
                    health['health'] = translation['unknown']
                    health['diagnosis'] = "No health check microflow defined"
                elif (health_response.get_result() ==
                        health_response.ERR_ACTION_NOT_FOUND):
                    # Admin action 'check_health' does not exist.
                    health['health'] = translation['unknown']
                    health['diagnosis'] = "No health check microflow defined"
                else:
                    health['health'] = translation['critical']
                    health['diagnosis'] = "Health check failed unexpectedly: %s" \
                                          % health_response.get_error()
            else:
                feedback = health_response.get_feedback()
                health['health'] = translation[feedback['health']]
                health['diagnosis'] = feedback['diagnosis'] if 'diagnosis' in feedback else ''
                health['response'] = health_response._json
        except Exception as e:
            logger.warn('Metrics: Failed to get health status, ' + str(e))
            health['health'] = translation['critical']
            health['diagnosis'] = "Health check failed unexpectedly: %s" % e

        return stats

    def _inject_m2ee_stats(self, stats):
        try:
            m2ee_stats, java_version = munin.get_stats_from_runtime(
                self.m2ee.client,
                self.m2ee.config
            )
            if 'sessions' in m2ee_stats:
                m2ee_stats['sessions']['user_sessions'] = {}
            m2ee_stats = munin.augment_and_fix_stats(
                m2ee_stats,
                self.m2ee.runner.get_pid(),
                java_version)

            critical_logs_count = len(
                self.m2ee.client.get_critical_log_messages()
            )
            m2ee_stats['critical_logs_count'] = critical_logs_count
            stats['mendix_runtime'] = m2ee_stats
        except Exception as e:
            logger.warn(
                'Metrics: Failed to get Mendix Runtime metrics, ' + str(e)
            )
        return stats

    def _inject_storage_stats(self, stats):
        storage_stats = {}
        try:
            storage_stats['get_number_of_files'] = self._get_number_of_files()
        except Exception as e:
            logger.warn(
                'Metrics: Failed to retrieve number of files, ' + str(e)
            )
        stats["storage"] = storage_stats
        return stats

    def _inject_database_stats(self, stats):
        database_stats = {}
        index_size = self._get_database_index_size()
        if index_size:
            database_stats['indexes_size'] = index_size
        table_size = self._get_database_table_size()
        if table_size:
            database_stats['tables_size'] = table_size
        mutations_stats = self._get_database_mutations()
        if mutations_stats:
            database_stats.update(mutations_stats)
        stats["database"] = database_stats
        return stats

    def _get_database_mutations(self):
        conn = self._get_db_conn()
        try:
            db_config = buildpackutil.get_database_config()
            with conn.cursor() as cursor:
                cursor.execute(
                    "select xact_commit, xact_rollback, tup_inserted, tup_updated, tup_deleted from pg_stat_database where datname = '%s';" % (
                        db_config['DatabaseName'],
                    )
                )
                rows = cursor.fetchall()
                return {
                    'xact_commit': int(rows[0][0]),
                    'xact_rollback': int(rows[0][1]),
                    'tup_inserted': int(rows[0][2]),
                    'tup_updated': int(rows[0][3]),
                    'tup_deleted': int(rows[0][4]),
                }
        except Exception as e:
            logger.warn(
                'Metrics: Failed to get database mutation stats, ' + str(e)
            )
        return None

    def _get_database_table_size(self):
        conn = self._get_db_conn()
        try:
            db_config = buildpackutil.get_database_config()
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_database_size('%s');" % (
                        db_config['DatabaseName'],
                    )
                )
                rows = cursor.fetchall()
                return int(rows[0][0])
        except Exception as e:
            logger.warn(
                'Metrics: Failed to get database data size, ' + str(e)
            )
        return None

    def _get_database_index_size(self):
        conn = self._get_db_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        SUM(pg_relation_size(quote_ident(indexrelname)::text)) AS index_size
                    FROM pg_tables t
                    LEFT OUTER JOIN pg_class c ON t.tablename=c.relname
                    LEFT OUTER JOIN
                        ( SELECT c.relname AS ctablename, ipg.relname AS indexname, x.indnatts AS number_of_columns, idx_scan, idx_tup_read, idx_tup_fetch, indexrelname, indisunique FROM pg_index x
                            JOIN pg_class c ON c.oid = x.indrelid
                            JOIN pg_class ipg ON ipg.oid = x.indexrelid
                            JOIN pg_stat_all_indexes psai ON x.indexrelid = psai.indexrelid )
                        AS foo
                        ON t.tablename = foo.ctablename
                    WHERE t.schemaname='public';
                    """
                )
                rows = cursor.fetchall()
                return int(rows[0][0])
        except Exception as e:
            logger.warn(
                'Metrics: Failed to get database index size, ' + str(e)
            )
        return None

    def _get_number_of_files(self):
        conn = self._get_db_conn()

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(id) from system$filedocument WHERE hascontents=true;'
            )
            rows = cursor.fetchall()
            if len(rows) == 0:
                raise Exception('Unexpected result from database query')
            return int(rows[0][0])

    def _get_db_conn(self):
        if self.db and self.db.closed != 0:
            self.db.close()
            self.db = None

        if not self.db:
            try:
                db_config = buildpackutil.get_database_config()
                if db_config['DatabaseType'] != 'PostgreSQL':
                    raise Exception(
                        'Metrics only supports postgresql, not %s'
                        % db_config['DatabaseType']
                    )
                host_and_port = db_config['DatabaseHost'].split(':')
                host = host_and_port[0]
                if len(host_and_port) > 1:
                    port = int(host_and_port[1])
                else:
                    port = 5432
                self.db = psycopg2.connect(
                    "options='-c statement_timeout=60s'",
                    database=db_config['DatabaseName'],
                    user=db_config['DatabaseUserName'],
                    password=db_config['DatabasePassword'],
                    host=host,
                    port=port,
                    connect_timeout=3,
                )
                self.db.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            except Exception as e:
                logger.warn('METRICS: ' + e.message)
        return self.db
