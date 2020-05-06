import json
import logging
import os
import subprocess
import threading
import time

from buildpack import util


class LoggingHeartbeatEmitterThread(threading.Thread):
    def __init__(self, interval):
        super().__init__()
        self.interval = interval

    def run(self):
        logging.debug(
            "Starting metrics emitter with interval %d", self.interval
        )
        counter = 1
        while True:
            logging.info(
                "MENDIX-LOGGING-HEARTBEAT: Heartbeat number %s", counter
            )
            time.sleep(self.interval)
            counter += 1


class LogFilterThread(threading.Thread):
    def __init__(self, log_ratelimit):
        super().__init__()
        self.log_ratelimit = log_ratelimit

    def run(self):
        try:
            while True:
                proc = subprocess.Popen(
                    [
                        "./bin/mendix-logfilter",
                        "-r",
                        self.log_ratelimit,
                        "-f",
                        "log/out.log",
                    ]
                )
                proc.wait()
                logging.warning(
                    "MENDIX LOGGING: Mendix logfilter crashed with return code "
                    "%s. This is nothing to worry about, we are restarting the "
                    "logfilter now.",
                    proc.returncode,
                )
        except Exception:
            logging.warning(
                "MENDIX LOGGING: Logging pipeline failed completely. To "
                "restore log availibility, restart your application.",
                exc_info=True,
            )


def set_up_logging_file():
    util.lazy_remove_file("log/out.log")
    os.mkfifo("log/out.log")
    log_ratelimit = os.getenv("LOG_RATELIMIT", None)
    if log_ratelimit is None:
        subprocess.Popen(
            [
                "sed",
                "--unbuffered",
                "s|^[0-9\-]\+\s[0-9:\.]\+\s||",
                "log/out.log",
            ]
        )
    else:
        log_filter_thread = LogFilterThread(log_ratelimit)
        log_filter_thread.daemon = True
        log_filter_thread.start()


def _transform_logging(nodes):
    res = []
    for k, v in nodes.items():
        res.append({"name": k, "level": v})
    return res


def update_config(m2ee):
    for k, v in os.environ.items():
        if k.startswith("LOGGING_CONFIG"):
            m2ee.set_log_levels(
                "*", nodes=_transform_logging(json.loads(v)), force=True
            )


def run():
    logging_interval = os.getenv(
        "METRICS_LOGGING_HEARTBEAT_INTERVAL", str(3600)
    )
    thread = LoggingHeartbeatEmitterThread(int(logging_interval))
    thread.setDaemon(True)
    thread.start()
