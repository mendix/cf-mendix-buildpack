import json
import time
from m2ee import logger, munin
import threading
import datetime

class MetricsEmitterThread(threading.Thread):

    def __init__(self, interval, m2ee):
        super(MetricsEmitterThread, self).__init__()
        self.interval = interval
        self.m2ee = m2ee

    def run(self):
        logger.debug('Starting metrics emitter with interval %d' % self.interval)
        while True:
            m2ee_stats, java_version = munin.get_stats_from_runtime(self.m2ee.client, self.m2ee.config)
            m2ee_stats = munin.augment_and_fix_stats(
                m2ee_stats,
                self.m2ee.runner.get_pid(),
                java_version)
            stats = {
                'version': '1.0',
                'timestamp': datetime.datetime.now().isoformat(),
                'mendix_runtime': m2ee_stats,
            }
            logger.info('MENDIX-METRICS: ' + json.dumps(stats))
            time.sleep(self.interval)
