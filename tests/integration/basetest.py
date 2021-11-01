import os
import unittest
import uuid
from distutils.util import strtobool

from buildpack import util

from .runner import CfLocalRunnerWithLocalDB, CfLocalRunnerWithPostgreSQL


class BaseTest(unittest.TestCase):
    _multiprocess_can_split_ = True

    ENV_PREFIX = "TEST_"

    # This class provides integration testing functionality with cf-local

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._runner = self._init_cflocal_runner(
            name="{}-{}".format(self._get_prefix(), self._get_random_id())
        )

    def _init_cflocal_runner(self, *args, **kwargs):
        return CfLocalRunnerWithLocalDB(*args, **kwargs)

    def _get_prefix(self):
        return os.environ.get(self.ENV_PREFIX + "PREFIX", "test")

    def _get_random_id(self):
        return str(uuid.uuid4()).split("-")[0]

    def start_container(self, *args, **kwargs):
        self._runner.start(*args, **kwargs)

    def terminate_container(self, *args, **kwargs):
        self._runner.stop(*args, **kwargs)

    def stage_container(self, package, env_vars=None, use_snapshot=False):
        package_url = None
        if util.is_url(package):
            package_url = package
        else:
            package_url = (
                "https://s3-eu-west-1.amazonaws.com/mx-buildpack-ci/" + package
            )

        return self._runner.stage(
            package=package_url,
            buildpack=os.path.join(
                os.getcwd(), "dist", "cf-mendix-buildpack.zip"
            ),
            env_vars=env_vars,
            use_snapshot=use_snapshot,
            password=os.environ.get(self.ENV_PREFIX + "MX_PASSWORD"),
            debug=bool(
                strtobool(os.environ.get(self.ENV_PREFIX + "DEBUG", "true"))
            ),
            host=os.environ.get(self.ENV_PREFIX + "HOST"),
            disk=os.environ.get(self.ENV_PREFIX + "DISK"),
            memory=os.environ.get(self.ENV_PREFIX + "MEMORY"),
        )

    def is_present_in_container(self, *args, **kwargs):
        return self._runner.is_path_present_in_container(*args, **kwargs)

    def await_container_health(self, *args, **kwargs):
        return self._runner.await_health(*args, **kwargs)

    def get_container_exitcode(self):
        return self._runner.get_exitcode()

    def tearDown(self):
        self._runner.destroy()

    def httpget(self, *args, **kwargs):
        return self._runner.httpget(*args, **kwargs)

    def httppost(self, *args, **kwargs):
        return self._runner.httppost(*args, **kwargs)

    def assert_app_running(self, *args, **kwargs):
        self.assertTrue(
            self._runner.is_app_running(*args, **kwargs),
            "Unexpected response code for assert_app_running",
        )

    def get_recent_logs(self):
        return self._runner.get_logs()

    def await_string_in_recent_logs(self, *args, **kwargs):
        return self._runner.await_string_in_logs(*args, **kwargs)

    def assert_string_in_recent_logs(self, substring):
        output = self._runner.get_logs()
        if substring in output:
            pass
        else:
            print(output)
            self.fail("Failed to find substring in recent logs: " + substring)

    def assert_string_not_in_recent_logs(self, substring):
        output = self._runner.get_logs()
        if substring in output:
            print(output)
            self.fail("Found substring in recent logs: " + substring)
        else:
            pass

    def assert_listening_on_port(self, *args, **kwargs):
        assert self._runner.is_process_listening_on_port(*args, **kwargs)

    def assert_running(self, *args, **kwargs):
        assert self._runner.is_process_running(*args, **kwargs)

    def query_mxadmin(self, *args, **kwargs):
        return self._runner.mxadmin(*args, **kwargs)

    def run_on_container(self, *args, **kwargs):
        return self._runner.run_on_container(*args, **kwargs)


class BaseTestWithPostgreSQL(BaseTest):
    def _init_cflocal_runner(self, *args, **kwargs):
        return CfLocalRunnerWithPostgreSQL(*args, **kwargs)
