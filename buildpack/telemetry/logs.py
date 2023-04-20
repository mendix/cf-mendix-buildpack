import json
import logging
import os
import subprocess
import threading
import time

from buildpack import util

NAMESPACE = ARTIFACT = "mendix-logfilter"


class LoggingHeartbeatEmitterThread(threading.Thread):
    def __init__(self, interval):
        super().__init__()
        self.interval = interval

    def run(self):
        logging.debug("Starting metrics emitter with interval %d", self.interval)
        counter = 1
        while True:
            logging.info("MENDIX-LOGGING-HEARTBEAT: Heartbeat number %s", counter)
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
                        os.path.abspath(
                            os.path.join(
                                ".local",
                                NAMESPACE,
                                ARTIFACT,
                            )
                        ),
                        "-r",
                        self.log_ratelimit,
                        "-f",
                        "log/out.log",
                    ]
                )
                proc.wait()
                logging.warning(
                    "MENDIX LOGGING: Mendix log filter crashed with return code "
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


def _redirect_logs():
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


def get_loglevels(env=None):
    if env is None:
        env = os.environ
    # Get log levels per node from environment
    for k, v in env.items():
        if k.startswith("LOGGING_CONFIG"):
            res = []
            for k, v in json.loads(v).items():
                res.append({"name": k, "level": v})
            return res


def run(m2ee):
    # Redirect logs
    _redirect_logs()

    # Start the logging heartbeat
    logging_interval = os.getenv("METRICS_LOGGING_HEARTBEAT_INTERVAL", str(3600))
    thread = LoggingHeartbeatEmitterThread(int(logging_interval))
    thread.daemon = True
    thread.start()


def stage(buildpack_dir, build_dir, cache_dir):
    logging.debug("Staging logging...")
    namespace = "mendix-logfilter"
    util.resolve_dependency(
        f"logs.{namespace}",
        os.path.join(build_dir, ".local", namespace),
        buildpack_dir=buildpack_dir,
        cache_dir=cache_dir,
    )
