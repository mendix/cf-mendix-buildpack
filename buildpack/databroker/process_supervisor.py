import subprocess
import logging


class DataBrokerProcess:
    def __init__(self, name, cmd, env):
        self.name = name
        self.cmd = cmd
        self.env = env
        self.__start()

    def __start(self):
        logging.debug("Starting process {}".format(self.name))
        self.__process_handle = subprocess.Popen(self.cmd, env=self.env)
        logging.debug(
            "Started process {} via command {}. Process Id: {}".format(
                self.name, self.cmd, self.__process_handle.pid
            )
        )

    def stop(self, timeout=30):
        logging.debug("Stopping process {}".format(self.name))
        try:
            self.__process_handle.terminate()
            self.__process_handle.wait(timeout=timeout)
        except ProcessLookupError:
            logging.debug("{} is already terminated".format(self.name))
        except subprocess.TimeoutExpired:
            logging.warn(
                "Timed out while waiting for process {} to terminate. Initiating kill".format(
                    self.name
                )
            )
            self.__process_handle.kill()
        except ProcessLookupError:
            logging.debug("{} is already terminated".format(self.name))
        except Exception as ex:
            logging.error(
                "Stop failed for {} process due to error {}".format(
                    self.name, ex
                )
            )

    def kill(self):
        logging.debug("Killing process {}".format(self.name))
        self.__process_handle.kill()

    def is_alive(self):
        if self.__process_handle.poll() is None:
            return True
        return False

    def restart(self):
        if self.is_alive():
            self.kill()
        self.__start()
