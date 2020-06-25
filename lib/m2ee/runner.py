#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
# http://www.mendix.com/
#

import subprocess
import os
import signal
import errno
from time import sleep

from .log import logger


class M2EERunner:
    # for background documentation, see:
    # http://www.faqs.org/faqs/unix-faq/programmer/faq/

    def __init__(self, config, client):
        self._config = config
        self._client = client
        self._read_pidfile()

    def _read_pidfile(self):
        pidfile = self._config.get_pidfile()
        try:
            with open(pidfile, "r") as pf:
                self._pid = int(pf.read().strip())
        except IOError as e:
            if e.errno != errno.ENOENT:
                logger.warn("Cannot read pidfile: %s" % e)
            self._pid = None
        except ValueError as e:
            logger.warn("Cannot read pidfile: %s" % e)
            self._pid = None

    def _write_pidfile(self):
        if self._pid:
            pidfile = self._config.get_pidfile()
            try:
                with open(pidfile, "w+") as pf:
                    pf.write("%s\n" % self._pid)
            except IOError as e:
                logger.error("Cannot write pidfile: %s" % e)

    def cleanup_pid(self):
        logger.debug("cleaning up pid & pidfile")
        self._pid = None
        pidfile = self._config.get_pidfile()
        if os.path.isfile(pidfile):
            os.unlink(pidfile)

    def get_pid(self):
        if not self._pid:
            self._read_pidfile()
        return self._pid

    def check_pid(self, pid=None):
        if pid is None:
            pid = self.get_pid()
        if not pid:
            return False
        try:
            os.kill(pid, 0)  # doesn't actually kill process
            return True
        except OSError:
            logger.trace("No process with pid %s, or not ours." % pid)
            return False

    def stop(self, timeout=5):
        self._client.shutdown()

        return self._wait_pid(timeout)

    def terminate(self, timeout=5):
        logger.debug("sending SIGTERM to pid %s" % self._pid)
        try:
            os.kill(self._pid, signal.SIGTERM)
        except OSError:
            # already gone or not our process?
            logger.debug("OSError! Process already gone?")
        return self._wait_pid(timeout)

    def kill(self, timeout=5):
        logger.debug("sending SIGKILL to pid %s" % self._pid)
        try:
            os.kill(self._pid, signal.SIGKILL)
        except OSError:
            # already gone or not our process?
            logger.debug("OSError! Process already gone?")
        return self._wait_pid(timeout)

    def start(self, timeout=60, step=0.25):
        if self.check_pid():
            logger.error("The application process is already started!")
            return False

        env = self._config.get_java_env()
        cmd = self._config.get_java_cmd()

        try:
            logger.trace("[%s] Forking now..." % os.getpid())
            pid = os.fork()
            if pid > 0:
                self._pid = None
                logger.trace(
                    "[%s] Waiting for intermediate process to "
                    "exit..." % os.getpid()
                )
                # prevent zombie process
                (waitpid, result) = os.waitpid(pid, 0)
                if result == 0:
                    logger.debug("The JVM process has been started.")
                    return True
                logger.error("Starting the JVM process did not succeed...")
                return False
        except OSError as e:
            logger.error(
                "Forking subprocess failed: %d (%s)\n" % (e.errno, e.strerror)
            )
            return
        logger.trace(
            "[%s] Now in intermediate forked process..." % os.getpid()
        )
        # decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0o022)

        logger.debug(
            "Environment to be used when starting the JVM: %s"
            % " ".join(["%s='%s'" % (k, v) for k, v in env.items()])
        )
        logger.debug(
            "Command line to be used when starting the JVM: %s" % " ".join(cmd)
        )

        # start java subprocess (second fork)
        logger.trace("[%s] Starting the JVM..." % os.getpid())
        try:
            proc = subprocess.Popen(cmd, close_fds=True, cwd="/", env=env,)
        except OSError as ose:
            if ose.errno == errno.ENOENT:
                logger.error(
                    "The java binary cannot be found in the default "
                    "search path!"
                )
                logger.error(
                    "By default, when starting the JVM, the "
                    "environment is not preserved. If you don't set "
                    "preserve_environment to true or specify PATH in "
                    "preserve_environment or custom_environment in "
                    "the m2ee section of your m2ee.yaml "
                    "configuration file, the search path is likely a "
                    "very basic default list like '/bin:/usr/bin'"
                )
                os._exit(1)
        # always write pid asap, so that monitoring can detect apps that should
        # be started but fail to do so
        self._pid = proc.pid
        logger.trace(
            "[%s] Writing JVM pid to pidfile: %s" % (os.getpid(), self._pid)
        )
        self._write_pidfile()
        # wait for m2ee to become available
        t = 0
        while t < timeout:
            sleep(step)
            dead = proc.poll()
            if dead is not None:
                logger.error(
                    "Java subprocess terminated with errorcode %s" % dead
                )
                logger.debug(
                    "[%s] Doing unclean exit from intermediate "
                    "process now." % os.getpid()
                )
                os._exit(1)
            if self.check_pid(proc.pid) and self._client.ping():
                break
            t += step
        if t >= timeout:
            logger.error("Timeout: Java subprocess takes too long to start.")
            logger.trace(
                "[%s] Doing unclean exit from intermediate process "
                "now." % os.getpid()
            )
            os._exit(1)
        logger.trace("[%s] Exiting intermediate process..." % os.getpid())
        os._exit(0)

    def _wait_pid(self, timeout=None, step=0.25):
        logger.trace("Waiting for process to disappear: timeout=%s" % timeout)
        if self.check_pid():
            if timeout is None:
                return False
            t = 0
            while t < timeout:
                sleep(step)
                if not self.check_pid():
                    break
                t += step
            if t >= timeout:
                logger.trace(
                    "Timeout: Process %s takes too long to "
                    "disappear." % self._pid
                )
                return False
        self.cleanup_pid()
        return True
