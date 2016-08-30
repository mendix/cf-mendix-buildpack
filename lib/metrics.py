import json
import time
import os
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
            m2ee_stats = munin.get_stats('values', self.m2ee.client, self.m2ee.config)
            stats = {
                'version': '1.0',
                'timestamp': datetime.datetime.now().isoformat(),
                'mendix_runtime': m2ee_stats,
            }
            logger.info('MENDIX-METRICS: ' + json.dumps(stats))
            time.sleep(self.interval)
