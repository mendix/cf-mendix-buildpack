import io
import json
import os
import re
import socket
import subprocess
import tarfile
import tempfile
import unittest
import uuid
from base64 import b64encode
from distutils.util import strtobool

import backoff
import requests
import yaml


class BaseTest(unittest.TestCase):
    _multiprocess_can_split_ = True

    # This class provides initialization and teardown functionality
    # for Mendix buildpack tests with cf-local (Docker)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._host = os.environ.get("TEST_HOST", "host.docker.internal")
        self._buildpack = os.path.join(
            os.getcwd(), "dist", "cf-mendix-buildpack.zip"
        )
        self._mx_password = os.environ.get("MX_PASSWORD", "Y0l0lop13#123")
        self._app_id = self._get_random_id()
        self._app_name = "{}-{}-{}".format(
            self._get_prefix(), self._app_id, "app"
        )
        self._debug = bool(strtobool(os.environ.get("TEST_DEBUG", "true")))
        self._disk = os.environ.get("TEST_DISK", "1G")
        self._memory = os.environ.get("TEST_MEMORY", "1G")

        self._workdir = tempfile.TemporaryDirectory()

        self._container_process = None
        self._container_port = None
        self._container_id = None
        self._package_path = None

    def _get_prefix(self):
        return os.environ.get("TEST_PREFIX", "test")

    def _get_random_id(self):
        return str(uuid.uuid4()).split("-")[0]

    def start_container(self, start_timeout=120, status="healthy"):
        try:
            self._container_process = subprocess.Popen(
                ("cf", "local", "run", self._app_name),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self._workdir.name,
            )
            process_stdout = io.TextIOWrapper(
                self._container_process.stdout, encoding="utf-8"
            )
            for line in process_stdout:
                match = re.match(r"Running .+ on port (\d+)\.\.\.", line)
                if match:
                    self._container_port = match.group(1)
                    break
        except (subprocess.CalledProcessError, Exception) as error:
            print(self.get_recent_logs())
            raise RuntimeError("Cannot start container", error)
        finally:
            process_stdout.close()

        @backoff.on_predicate(
            backoff.constant, interval=1, max_time=5, logger=None
        )
        def _await_container_id():
            return self._get_container_id()

        self._container_id = _await_container_id()

        is_status_reached = self.await_container_status(status, start_timeout)

        if not is_status_reached:
            print(self.get_recent_logs())
            raise RuntimeError(
                "Container did not reach [{}] status within [{}] seconds".format(
                    status, start_timeout
                )
            )

    def stage_container(self, package_name, env_vars=None, use_snapshot=False):
        package_url = os.environ.get(
            "PACKAGE_URL",
            "https://s3-eu-west-1.amazonaws.com/mx-buildpack-ci/"
            + package_name,
        )
        self._package_path = os.path.join(
            self._workdir.name, "{}-{}".format(self._app_name, package_name)
        )

        self._cmd(
            ("wget", "--quiet", "-c", "-O", self._package_path, package_url)
        )

        environment = {
            "ADMIN_PASSWORD": self._mx_password,
            "DEBUGGER_PASSWORD": self._mx_password,
            "BUILDPACK_XTRACE": self._debug,
            "DEVELOPMENT_MODE": "true",
            "USE_DATA_SNAPSHOT": use_snapshot,
        }

        environment.update(self._get_database_environment())

        if env_vars is not None:
            environment.update(env_vars)

        configuration = {
            "applications": [
                {
                    "name": self._app_name,
                    "buildpacks": [self._buildpack],
                    "memory": self._memory,
                    "disk": self._disk,
                    "env": environment,
                }
            ]
        }

        with open(os.path.join(self._workdir.name, "local.yml"), "w") as file:
            yaml.dump(configuration, file)

        result = self._cmd(
            ("cf", "local", "stage", self._app_name, "-p", self._package_path)
        )

        if not result[1]:
            raise RuntimeError(
                "Could not stage container: {}".format(result[0])
            )

        return result

    def is_present_in_container(self, path):
        path_in_tar = os.path.join("app", path)
        with tarfile.open(
            os.path.join(
                self._workdir.name, "{}.{}".format(self._app_name, "droplet")
            ),
            "r",
        ) as tar:
            return any(path_in_tar in name for name in tar.getnames())

    def _get_database_environment(self):
        return {
            "MXRUNTIME_DatabaseName": "test",
            "MXRUNTIME_DatabaseJdbcUrl": "jdbc:hsqldb:mem:sampledb",
            "MXRUNTIME_DatabaseType": "HSQLDB",
        }

    def await_container_status(self, status, max_time=120):
        @backoff.on_predicate(
            backoff.constant, interval=1, max_time=max_time, logger=None
        )
        def _await_container_status(status):
            return self._get_container_status() == status

        return _await_container_status(status)

    def _get_container_id(self):
        return self._cmd(
            ("docker", "ps", "-aq", "-f", "name={}*".format(self._app_name))
        )[0]

    def _get_container_status(self):
        status = self._cmd(
            (
                "docker",
                "inspect",
                "-f",
                "{{.State.Health.Status}}",
                self._container_id,
            )
        )
        if not status[1]:
            return None
        return status[0]

    def _remove_container(self, id_or_name=None):
        if not id_or_name:
            id_or_name = self._container_id
        result = self._cmd(("docker", "rm", "-f", id_or_name))
        if not result[1]:
            raise RuntimeError(
                "Cannot remove container: {}".format(result[0].strip("\n"))
            )

    def tearDown(self):
        if self._container_process:
            self._container_process.terminate()
            self._remove_container()
        self._workdir.cleanup()

    def httpget(self, path=None, **kwargs):
        return self._httprequest("GET", path, **kwargs)

    def httppost(self, path=None, **kwargs):
        return self._httprequest("POST", path, **kwargs)

    def _httprequest(self, method, path=None, **kwargs):
        uri = "http://localhost:{}".format(self._container_port)
        if path:
            uri += path
        return requests.request(method, uri, **kwargs)

    def assert_app_running(self, path="/xas/", code=401):
        r = self.httpget(path)
        self.assertEqual(
            r.status_code,
            code,
            "Unexpected response code for assert_app_running",
        )

    def get_recent_logs(self):
        return self._cmd(
            ("docker", "logs", "-t", "--tail", "all", self._container_id)
        )[0]

    def await_string_in_recent_logs(self, substring, max_time=30):
        @backoff.on_predicate(
            backoff.constant, interval=1, max_time=max_time, logger=None
        )
        def _await_string_in_recent_logs(substring):
            return substring in self.get_recent_logs()

        return _await_string_in_recent_logs(substring)

    def assert_string_in_recent_logs(self, substring):
        output = self.get_recent_logs()
        if substring in output:
            pass
        else:
            print(output)
            self.fail("Failed to find substring in recent logs: " + substring)

    def assert_string_not_in_recent_logs(self, substring):
        output = self.get_recent_logs()
        if substring in output:
            print(output)
            self.fail("Found substring in recent logs: " + substring)
        else:
            pass

    def assert_listening_on_port(self, port, process):
        output = self.run_on_container(
            "lsof -i | grep '^{}.*:{}'".format(process, port)
        )
        assert output is not None
        assert str(output).find(process) >= 0

    def assert_running(self, process):
        output = self.run_on_container("ps aux | grep {}".format(process))
        assert output is not None
        assert str(output).find(process) >= 0

    def _cmd(self, command):
        try:
            return (
                subprocess.check_output(
                    command, cwd=self._workdir.name, stderr=subprocess.STDOUT
                )
                .decode("utf-8")
                .strip(),
                True,
            )
        except subprocess.CalledProcessError as e:
            return e.output.decode("utf-8").strip(), False

    def _bytes(self, s):
        return s.encode("utf-8")

    def query_mxadmin(self, command):
        basic_auth = "MxAdmin:{}".format(self._mx_password)
        basic_auth_base64 = b64encode(self._bytes(basic_auth)).decode("utf-8")
        m2ee_auth_base64 = b64encode(self._bytes(self._mx_password)).decode(
            "utf-8"
        )

        return self.httppost(
            "/_mxadmin/",
            data=json.dumps(command),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Basic {}".format(basic_auth_base64),
                "X-M2EE-Authentication": m2ee_auth_base64,
            },
            timeout=15,
        )

    def run_on_container(self, command, target_container=None):
        if target_container is None:
            target_container = self._container_id

        result = self._cmd(
            ("docker", "exec", target_container, "bash", "-c", command)
        )
        if not result[1]:
            raise RuntimeError(
                "Error running command on container: {}".format(result[0])
            )
        return result[0]


class BaseTestWithPostgreSQL(BaseTest):

    # This class adds a PostgreSQL database to test on
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._database_container_name = "{}-{}-{}".format(
            self._get_prefix(), self._app_id, "db"
        )
        self._database_port = None
        self._database_user = "test"
        self._database_password = "test"
        self._database_name = "test"
        self._database_postgres_version = 9
        self._database_postgres_image = "postgres"

    def _get_database_environment(self):
        # return {
        #     "MXRUNTIME_DatabaseType": "PostgreSQL",
        #     "MXRUNTIME_DatabaseHost": "{}:{}".format(
        #         self._database_host, self._database_port
        #     ),
        #     "MXRUNTIME_DatabaseName": self._database_name,
        #     "MXRUNTIME_DatabaseUserName": self._database_user,
        #     "MXRUNTIME_DatabasePassword": self._database_password,
        # }
        return {
            "DATABASE_URL": "postgresql://{}:{}@{}:{}/{}".format(
                self._database_user,
                self._database_password,
                self._host,
                self._database_port,
                self._database_name,
            )
        }

    def stage_container(self, package_name, env_vars=None):
        # The PostgreSQL container has to start here:
        # We need the port number before staging

        result = self._cmd(
            (
                "docker",
                "run",
                "--name",
                self._database_container_name,
                "-p",
                str(5432),
                "-e",
                "POSTGRES_USER={}".format(self._database_user),
                "-e",
                "POSTGRES_PASSWORD={}".format(self._database_password),
                "-e",
                "POSTGRES_DB={}".format(self._database_name),
                "-d",
                "{}:{}".format(
                    self._database_postgres_image,
                    self._database_postgres_version,
                ),
            )
        )

        if not result[1]:
            raise RuntimeError(
                "Cannot create database container: {}".format(result[0])
            )

        result = self._cmd(("docker", "port", self._database_container_name))

        if not result[1]:
            raise RuntimeError(
                "Cannot get database container port: {}".format(result[0])
            )

        self._database_port = result[0].split(":")[1]

        # update database_host with correct exposed port of db
        if env_vars and "MXRUNTIME_DatabaseHost" in env_vars:
            env_vars["MXRUNTIME_DatabaseHost"] = "{}:{}".format(
                self._host, self._database_port
            )

        return super().stage_container(
            package_name=package_name, env_vars=env_vars
        )

    def start_container(self, start_timeout=120, status="healthy"):
        # Wait until the database is up
        @backoff.on_predicate(backoff.expo, lambda x: x > 0, max_time=30)
        def _await_database():
            return socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            ).connect_ex(("localhost", int(self._database_port)))

        _await_database()

        super().start_container(start_timeout=start_timeout, status=status)

    def tearDown(self):
        self._remove_container(self._database_container_name)
        super().tearDown()
