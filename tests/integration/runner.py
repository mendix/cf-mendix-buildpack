#! /usr/bin/env python
import abc
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
from base64 import b64encode

import backoff
import click
import randomname
import requests
import yaml

# Hacks to find project root and make script runnable in most cases
PROJECT_ROOT_PATH = None
if "__file__" in vars():
    PROJECT_ROOT_PATH = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    )
else:
    PROJECT_ROOT_PATH = os.getcwd()
sys.path.append(PROJECT_ROOT_PATH)

# TODO Understand if this needs to be here or can be moved to the top of file
from buildpack import util  # noqa: E402


class CfLocalRunner(metaclass=abc.ABCMeta):

    # This class provides functionality to run a Mendix application locally
    # with cf-local (Docker)

    def __init__(self, name):
        if not name:
            raise ValueError("name has to contain a value")
        self._app_name = name

        self._workdir = tempfile.TemporaryDirectory()

        self._init_container_state(name)

    def _init_container_state(self, name):
        self._container_name = name + "-app"
        self._container_process = None
        self._container_id = self._get_container_id(self._container_name)
        try:
            self._container_port = self._get_container_host_port(
                self._container_id, 8080
            )
        except:  # noqa: E722
            self._container_port = None

    def stage(
        self,
        package,
        buildpack,
        host=None,
        disk=None,
        memory=None,
        env_vars=None,
        use_snapshot=False,
        password=None,
        debug=True,
    ):

        self._check_for_cflocal()

        if not buildpack:
            raise ValueError("buildpack has to contain a value")
        self._buildpack = buildpack

        if not password:
            self._mx_password = "Y0l0lop13#123"
        else:
            self._mx_password = password
        self._debug = debug

        if not host:
            self._host = "host.docker.internal"
        else:
            self._host = host

        if not disk:
            self._disk = "1G"
        else:
            self._disk = disk
        if not memory:
            self._memory = "1G"
        else:
            self._memory = memory

        package_basename = package.rsplit("/", 1)[-1]

        self._package_path = os.path.join(
            self._workdir.name,
            "{}-{}".format(self._app_name, package_basename),
        )

        if util.is_url(package):
            util.download(package, self._package_path)
        elif util.is_path_accessible(package):
            shutil.copyfile(package, self._package_path)
        else:
            raise ValueError("Package is not a URL or valid path")

        configuration = {
            "applications": [
                {
                    "name": self._container_name,
                    "buildpacks": [self._buildpack],
                    "memory": self._memory,
                    "disk": self._disk,
                    "env": self._setup_environment(env_vars, use_snapshot),
                }
            ]
        }

        with open(os.path.join(self._workdir.name, "local.yml"), "w") as file:
            yaml.dump(configuration, file)

        result = self._cmd(
            (
                "cf",
                "local",
                "stage",
                self._container_name,
                "-p",
                self._package_path,
            )
        )

        if not result[1]:
            raise RuntimeError("Could not stage container: {}".format(result[0]))

        return result

    def start(self, start_timeout=180, health="healthy"):
        self._check_for_cflocal()

        if not self._container_id:
            try:
                self._container_process = subprocess.Popen(
                    ("cf", "local", "run", self._container_name),
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
                print(self.get_logs())
                raise RuntimeError("Cannot start container", error)
            finally:
                process_stdout.close()

            @backoff.on_predicate(backoff.constant, interval=1, max_time=5, logger=None)
            def _await_container_id():
                return self._get_container_id(self._container_name)

            self._container_id = _await_container_id()
        else:
            self._cmd(
                (
                    "docker",
                    "start",
                    "{}".format(self._container_id),
                )
            )[0]

        is_status_reached = self.await_health(health, start_timeout)

        if not is_status_reached:
            print(self.get_logs())
            raise RuntimeError(
                "Container did not reach [{}] status within [{}] seconds".format(
                    health, start_timeout
                )
            )

    def stop(self, signal="SIGTERM"):
        if signal == "SIGTERM" and self._container_process:
            self._container_process.terminate()
        if self._container_id:
            return self._cmd(
                (
                    "docker",
                    "kill",
                    "--signal={}".format(signal),
                    "{}".format(self._container_id),
                )
            )[0]

    def destroy(self):
        if self._container_process:
            self._container_process.terminate()
        self._remove_all_containers()
        self._workdir.cleanup()

    def get_logs(self):
        return self._cmd(("docker", "logs", "-t", "--tail", "all", self._container_id))[
            0
        ]

    def get_exitcode(self):
        status = self._cmd(
            (
                "docker",
                "inspect",
                "-f",
                "{{.State.ExitCode}}",
                self._container_id,
            )
        )
        if not status[1]:
            return None
        return int(status[0])

    def get_app_name(self):
        return self._app_name

    def get_host(self):
        return self._host

    def get_mx_password(self):
        return self._mx_password

    def get_container_port(self):
        return self._container_port

    def run_on_container(self, command, target_container=None):
        if target_container is None:
            target_container = self._container_id

        result = self._cmd(("docker", "exec", target_container, "bash", "-c", command))
        if not result[1]:
            raise RuntimeError(
                "Error running command on container: {}".format(result[0])
            )
        return result[0]

    def httpget(self, path=None, **kwargs):
        return self._httprequest("GET", path, **kwargs)

    def httppost(self, path=None, **kwargs):
        return self._httprequest("POST", path, **kwargs)

    def mxadmin(self, command):
        basic_auth = "MxAdmin:{}".format(self._mx_password)
        basic_auth_base64 = b64encode(self._bytes(basic_auth)).decode("utf-8")
        m2ee_auth_base64 = b64encode(self._bytes(self._mx_password)).decode("utf-8")

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

    def is_app_running(self, path="/xas/", code=401):
        r = self.httpget(path)
        return r.status_code == code

    def is_process_running(self, process):
        output = self.run_on_container("ps aux | grep {}".format(process))
        return output is not None and str(output).find(process) >= 0

    def is_process_listening_on_port(self, port, process):
        output = self.run_on_container(
            "lsof -i | grep '^{}.*:{}'".format(process, port)
        )
        return output is not None

    def is_path_present_in_container(self, path):
        path_in_tar = os.path.join("app", path)
        with tarfile.open(
            os.path.join(
                self._workdir.name,
                "{}.{}".format(self._container_name, "droplet"),
            ),
            "r",
        ) as tar:
            return any(path_in_tar in name for name in tar.getnames())

    def await_health(self, health, max_time=120):
        @backoff.on_predicate(
            backoff.constant, interval=1, max_time=max_time, logger=None
        )
        def _await_container_status(health):
            return self._get_container_health() == health

        return _await_container_status(health)

    def await_string_in_logs(self, substring, max_time=30):
        @backoff.on_predicate(
            backoff.constant, interval=1, max_time=max_time, logger=None
        )
        def _await_string_in_logs(substring):
            return substring in self.get_logs()

        return _await_string_in_logs(substring)

    def _setup_environment(self, env_vars, use_snapshot):
        environment = {
            "ADMIN_PASSWORD": self._mx_password,
            "DEBUGGER_PASSWORD": self._mx_password,
            "BUILDPACK_XTRACE": self._debug,
            "DEVELOPMENT_MODE": "true",
            "USE_DATA_SNAPSHOT": use_snapshot,
        }

        environment.update(self._get_environment(env_vars))

        if env_vars is not None:
            environment.update(env_vars)

        return environment

    @abc.abstractmethod
    def _get_environment(self, env_vars):
        return

    def _check_for_cflocal(self):
        if (
            subprocess.run(
                ["cf", "local", "version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            > 0
        ):
            raise RuntimeError(
                "cf-local not found. "
                "Please ensure that you have installed the CF CLI "
                "and the cf-local plugin."
            )

    def _bytes(self, s):
        return s.encode("utf-8")

    def _httprequest(self, method, path=None, **kwargs):
        uri = f"http://localhost:{self._container_port}"
        if path:
            uri += path
        return requests.request(method, uri, **kwargs)

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

    def _get_container_host_port(self, id_or_name, guest_port):
        result = self._cmd(
            (
                "docker",
                "port",
                id_or_name,
                "{}/tcp".format(guest_port),
            ),
        )
        if not result[1]:
            raise RuntimeError("Cannot get container port: {}".format(result[0]))
        return int(result[0].split(":")[-1].rstrip())

    def _get_container_ids(self, name):
        return self._cmd(("docker", "ps", "-aqf", "name={}*".format(name)))[0].rsplit(
            "\n"
        )

    def _get_container_id(self, name):
        return self._get_container_ids(name)[0]

    def _get_container_health(self):
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

    def _remove_all_containers(self, name_prefix=None):
        if not name_prefix:
            name_prefix = self._app_name
        [self._remove_container(id) for id in self._get_container_ids(name_prefix)]

    def _remove_container(self, id_or_name=None):
        if not id_or_name:
            id_or_name = self._container_id
        if id_or_name:
            result = self._cmd(("docker", "rm", "-f", id_or_name))
            if not result[1]:
                raise RuntimeError(
                    "Cannot remove container: {}".format(result[0].strip("\n"))
                )


class CfLocalRunnerWithLocalDB(CfLocalRunner):
    def _get_environment(self, env_vars):
        return {
            "MXRUNTIME_DatabaseName": "test",
            "MXRUNTIME_DatabaseJdbcUrl": "jdbc:hsqldb:mem:sampledb",
            "MXRUNTIME_DatabaseType": "HSQLDB",
        }


class CfLocalRunnerWithPostgreSQL(CfLocalRunner):

    # This class adds a PostgreSQL database to test on
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._database_container_name = "{}-{}".format(self._app_name, "db")
        self._database_port = None
        self._database_user = "user"
        self._database_password = "password"
        self._database_name = "mendix"
        self._database_postgres_version = 9
        self._database_postgres_image = "postgres"

    def _get_environment(self, env_vars):
        return {
            "DATABASE_URL": "postgresql://{}:{}@{}:{}/{}".format(
                self._database_user,
                self._database_password,
                self._host,
                self._database_port,
                self._database_name,
            )
        }

    def stage(self, *args, **kwargs):
        # The PostgreSQL container has to start here
        # We need the port number before staging
        DEFAULT_PORT = 5432
        result = self._cmd(
            (
                "docker",
                "run",
                "--name",
                self._database_container_name,
                "-p",
                str(DEFAULT_PORT),
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
            raise RuntimeError("Cannot create database container: {}".format(result[0]))

        self._database_port = self._get_container_host_port(
            self._database_container_name, DEFAULT_PORT
        )

        # update database_host with correct exposed port of db
        env_vars = kwargs["env_vars"]
        if env_vars and "MXRUNTIME_DatabaseHost" in env_vars:
            env_vars["MXRUNTIME_DatabaseHost"] = "{}:{}".format(
                self._host, self._database_port
            )

        return super().stage(*args, **kwargs)

    def start(self, start_timeout=180, health="healthy"):
        # Wait until the database is up
        @backoff.on_predicate(backoff.expo, lambda x: x > 0, max_time=30)
        def _await_database():
            return socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(
                ("localhost", int(self._database_port))
            )

        _await_database()

        super().start(start_timeout=start_timeout, health=health)


# Command Line Interface
@click.group()
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Enables verbose output.",
)
@click.pass_context
def cli(ctx, verbose):
    ctx.obj = {"verbose": verbose}


def _create_runner(name, with_db=False):
    if not with_db:
        return CfLocalRunnerWithLocalDB(name)
    return CfLocalRunnerWithPostgreSQL(name)


def _get_env_variable(env_option):
    result = env_option.rsplit("=")
    if len(result) != 2:
        raise ValueError(
            f"Invalid environment option {env_option}. "
            "Must be formatted KEY=VALUE or be a valid file."
        )
    return result


def _get_absolute_path(path):
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return os.path.abspath(path)


def _get_env_variables(env_option):
    options = []
    option_path = _get_absolute_path(env_option)
    if util.is_path_accessible(option_path):
        with open(option_path, "r") as f:
            options = [line.rstrip() for line in f]
    else:
        options = [env_option]
    return [_get_env_variable(option) for option in options]


def _parse_env_options(env_options):
    return dict([j for i in [_get_env_variables(k) for k in env_options] for j in i])


@cli.command(help="Stages and starts a Mendix application.")
@click.option(
    "-n",
    "--name",
    default=randomname.get_name(),
    help="Sets the name of the application.",
)
@click.option(
    "-p",
    "--password",
    help="Sets the adminstrator password for the application.",
)
@click.option(
    "-e",
    "--env",
    multiple=True,
    help="Sets an environment variable (KEY=VALUE) for the application. "
    "Providing a file with environment variables and multiple options are allowed.",
)
@click.option(
    "--use-snapshot",
    is_flag=True,
    default=False,
    help="Enables using an included application snapshot in the provided package.",
)
@click.option(
    "--with-db",
    is_flag=True,
    default=False,
    help="Enables a PostgreSQL sidecar container as application database.",
)
@click.option(
    "--debug",
    is_flag=True,
    default=True,
    help="Enables or disables application debug logs.",
)
@click.option(
    "--host",
    default="host.docker.internal",
    help="Sets the internal Docker host.",
)
@click.argument("package")
@click.pass_context
def run(ctx, name, password, package, env, use_snapshot, with_db, debug, host):
    verbose = ctx.obj["verbose"]
    runner = _create_runner(name, with_db=with_db)
    buildpack = os.path.join(PROJECT_ROOT_PATH, "dist", "cf-mendix-buildpack.zip")
    if not util.is_path_accessible(buildpack):
        raise RuntimeError(
            "Cannot find buildpack at {}. Please run make build first.".format(
                buildpack
            )
        )
    try:
        env_vars = None
        if verbose:
            click.echo("Staging application...")
            env_vars = _parse_env_options(env)
        if verbose:
            click.echo("Environment: {}".format(env_vars))
        stage = runner.stage(
            _get_absolute_path(package),
            buildpack=buildpack,
            host=host,
            env_vars=env_vars,
            use_snapshot=use_snapshot,
            password=password,
            debug=debug,
        )
    except Exception as ex:
        click.echo(ex)
        runner.destroy()
        sys.exit(1)
    if not stage[1]:
        runner.destroy()
        sys.exit(1)
    if verbose:
        click.echo(stage[0])

    try:
        if verbose:
            click.echo("Starting application {}...".format(runner.get_app_name()))
        runner.start()
    except Exception as ex:
        runner.destroy()
        click.echo(ex)

    exitcode = runner.get_exitcode()
    if verbose:
        click.echo(runner.get_logs())
    if exitcode == 0:
        click.echo(
            "Application {} is running on localhost:{} with password {}.".format(
                runner.get_app_name(),
                runner.get_container_port(),
                runner.get_mx_password(),
            )
        )
    else:
        click.echo("Could not start application.")
        runner.destroy()
    sys.exit(exitcode)


@cli.command(help="Removes a running application.")
@click.argument("application")
@click.pass_context
def rm(ctx, application):
    runner = _create_runner(application)
    runner.destroy()


@cli.command(help="Prints logs for an application.")
@click.argument("application")
@click.pass_context
def logs(ctx, application):
    runner = _create_runner(application)
    click.echo(runner.get_logs())


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
