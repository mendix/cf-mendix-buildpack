import os
import sys
import json
import time
from m2ee import logger, munin
import threading
import datetime
import urlparse

BUILDPACK_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

sys.path.insert(0, os.path.join(BUILDPACK_DIR, 'lib'))
import buildpackutil
import psycopg2


class MetricsEmitterThread(threading.Thread):

    def __init__(self, interval, m2ee):
        super(MetricsEmitterThread, self).__init__()
        self.interval = interval
        self.m2ee = m2ee

    def run(self):
        logger.debug('Starting metrics emitter with interval %d' % self.interval)
        while True:
            try:
                m2ee_stats = self._get_m2ee_stats()
                s3_stats = self._get_s3_stats()
                stats = {
                    'version': '1.0',
                    'timestamp': datetime.datetime.now().isoformat(),
                    'mendix_runtime': m2ee_stats,
                }

                if s3_stats:
                    stats["mendix_storage"] = s3_stats

                logger.info('MENDIX-METRICS: ' + json.dumps(stats))
            except Exception as e:
                logger.warn('Failed to emit Mendix runtime metrics: ' + str(e))

            time.sleep(self.interval)

    def _get_m2ee_stats(self):
        m2ee_stats, java_version = munin.get_stats_from_runtime(self.m2ee.client, self.m2ee.config)
        m2ee_stats = munin.augment_and_fix_stats(
            m2ee_stats,
            self.m2ee.runner.get_pid(),
            java_version)

        critical_logs_count = len(self.m2ee.client.get_critical_log_messages())
        m2ee_stats['critical_logs_count'] = critical_logs_count

        return m2ee_stats

    def _get_s3_stats(self):
        resulting_stats = {
            'number_of_files': 0,
            'total_size': 0
        }
        vcap_services = buildpackutil.get_vcap_services_data()
        try:
            uri = vcap_services['PostgreSQL'][0]['credentials']['uri']
            result = urlparse.urlparse(uri)
            username = result.username
            password = result.password
            database = result.path[1:]
            hostname = result.hostname
            conn = psycopg2.connect(
                database=database,
                user=username,
                password=password,
                host=hostname
            )
        except Exception as e:
            logger.error('MENDIX-METRICS: ' + e.message)
            return None
        cur = conn.cursor()
        # SELECT COUNT(id) from system$filedocument WHERE hascontents=true;
        # SELECT sum(size) from system$filedocument;
        cur.execute("""SELECT * from system$filedocument""")
        colnames = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        if len(rows) == 0:
            return None
        logger.info('MENDIX-METRICS: ' + str(colnames))
        logger.info('MENDIX-METRICS: ' + str(rows))
        return resulting_stats
