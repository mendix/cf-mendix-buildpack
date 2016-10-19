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

            stats = {
                'version': '1.0',
                'timestamp': datetime.datetime.now().isoformat(),
            }
            stats = self._inject_m2ee_stats(stats)
            stats = self._inject_storage_stats(stats)

            logger.info('MENDIX-METRICS: ' + json.dumps(stats))

            time.sleep(self.interval)

    def _inject_m2ee_stats(self, stats):
        try:
            m2ee_stats, java_version = munin.get_stats_from_runtime(
                self.m2ee.client,
                self.m2ee.config
            )
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

    def _get_number_of_files(self):
        conn = self._get_db_conn()

        cur = conn.cursor()
        cur.execute(
            'SELECT COUNT(id) from system$filedocument WHERE hascontents=true;'
        )
        rows = cur.fetchall()

        if len(rows) == 0:
            raise Exception('Unexpected result from database query')

        return int(rows[0][0])

    def _get_db_conn(self):
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
                    database=db_config['DatabaseName'],
                    user=db_config['DatabaseUserName'],
                    password=db_config['DatabasePassword'],
                    host=host,
                    port=port,
                )
            except Exception as e:
                logger.warn('METRICS: ' + e.message)
        return self.db
