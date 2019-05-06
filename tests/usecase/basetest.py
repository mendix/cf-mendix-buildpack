from base64 import b64encode
import os
import json
import subprocess
import unittest
import uuid
import requests
import tempfile


class BaseTest(unittest.TestCase):
    _multiprocess_can_split_ = True

    """
    BaseTest class provides initialization and teardown functionality
    for mendix buildpack tests that utilize cloudfoundry
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not os.environ.get("TRAVIS_BRANCH"):
            current_branch = subprocess.check_output(
                (
                    "git",
                    "rev-parse",
                    "--symbolic-full-name",
                    "--abbrev-ref",
                    "HEAD",
                )
            ).decode("utf-8")
        else:
            current_branch = "master"
        self.branch_name = os.environ.get("TRAVIS_BRANCH", current_branch)

        self.cf_domain = os.environ.get("CF_DOMAIN")
        self.assertIsNotNone(
            self.cf_domain, "CF_DOMAIN env variable is not configured"
        )
        self.buildpack_repo = os.environ.get(
            "BUILDPACK_REPO",
            "https://github.com/mendix/cf-mendix-buildpack.git",
        )
        self.buildpack = os.environ.get(
            "BUILDPACK", "{}#{}".format(self.buildpack_repo, self.branch_name)
        )
        self.mx_password = os.environ.get("MX_PASSWORD", "Y0l0lop13#123")
        self.app_id = str(uuid.uuid4()).split("-")[0]
        self.subdomain = "ops-" + self.app_id
        self.app_name = "%s.%s" % (self.subdomain, self.cf_domain)

    def setUp(self):
        self.cf_home = tempfile.TemporaryDirectory()
        os.mkdir(os.path.join(self.cf_home.name, ".cf"))
        self.cmd(
            (
                "cf",
                "login",
                "-a",
                os.environ["CF_ENDPOINT"],
                "-u",
                os.environ["CF_USER"],
                "-p",
                os.environ["CF_PASSWORD"],
                "-o",
                os.environ["CF_ORG"],
                "-s",
                os.environ["CF_SPACE"],
            )
        )

    def startApp(self, start_timeout=25, expect_failure=False):
        try:
            env = {}
            if start_timeout:
                env["CF_STARTUP_TIMEOUT"] = str(start_timeout)
            self.cmd(("cf", "start", self.app_name), env=env)
        except subprocess.CalledProcessError as e:
            if expect_failure:
                return
            else:
                print(e.output)
                print(self.get_recent_logs())
                raise e
        if expect_failure:
            raise Exception("App unexpectedly started successfully")

    def setUpCF(
        self, package_name, health_timeout=180, env_vars=None, instances=1
    ):
        try:
            self._setUpCF(
                package_name,
                health_timeout,
                env_vars=env_vars,
                instances=instances,
            )
        except Exception:
            self.tearDown()
            raise

    def _setUpCF(
        self, package_name, health_timeout, env_vars=None, instances=1
    ):
        self.package_name = package_name
        self.package_url = os.environ.get(
            "PACKAGE_URL",
            "https://s3-eu-west-1.amazonaws.com/mx-buildpack-ci/"
            + package_name,
        )

        self.cmd(
            (
                "wget",
                "--quiet",
                "-c",
                "-O",
                self.app_id + self.package_name,
                self.package_url,
            )
        )
        try:
            self.cmd(
                (
                    "cf",
                    "push",
                    self.app_name,
                    "-d",
                    self.cf_domain,
                    "-p",
                    self.app_id + self.package_name,
                    "-n",
                    self.subdomain,
                    "--no-start",
                    "-k",
                    "3G",
                    "-m",
                    "2G",
                    "-t",
                    str(health_timeout),
                    "-i",
                    str(instances),
                    "-b",
                    self.buildpack,
                )
            )

        except subprocess.CalledProcessError as e:
            print(e.output.decode("utf-8"))
            raise
        finally:
            # remove the downloaded file
            os.remove(self.app_id + self.package_name)

        self.cmd(("./create-app-services.sh", self.app_name))

        app_guid = self.cmd(("cf", "app", self.app_name, "--guid")).strip()

        environment = {
            "ADMIN_PASSWORD": self.mx_password,
            "DEBUGGER_PASSWORD": self.mx_password,
            "DEVELOPMENT_MODE": "true",
            "S3_USE_SSE": "true",
            "USE_DATA_SNAPSHOT": "true",
        }

        if env_vars is not None:
            environment.update(env_vars)

        self.cmd(
            (  # check_call prints the output, no thanks
                "cf",
                "curl",
                "-X",
                "PUT",
                "/v2/apps/%s" % app_guid,
                "-d",
                json.dumps({"environment_json": environment}),
            )
        )

    def tearDown(self):
        self.cmd(("./delete-app.sh", self.app_name))
        self.cf_home.cleanup()

    def assert_app_running(self, path="/xas/", code=401):
        full_uri = "https://" + self.app_name + path
        r = requests.get(full_uri)
        self.assertEqual(
            r.status_code,
            code,
            "unexpected response code for assert_app_running",
        )

    def get_recent_logs(self):
        return self.cmd(("cf", "logs", self.app_name, "--recent"))

    def assert_string_in_recent_logs(self, substring):
        output = self.get_recent_logs()
        if output.find(substring) > 0:
            pass
        else:
            print(output)
            self.fail("Failed to find substring in recent logs: " + substring)

    def assert_string_not_in_recent_logs(self, substring):
        output = self.get_recent_logs()
        if output.find(substring) > 0:
            print(output)
            self.fail("Found substring in recent logs: " + substring)
        else:
            pass

    def cmd(self, command, env=None):
        effective_env = os.environ.copy()
        effective_env.update({"CF_HOME": self.cf_home.name})
        if env:
            effective_env.update(env)
        try:
            return subprocess.check_output(
                command, stderr=subprocess.PIPE, env=effective_env
            ).decode("utf-8")
        except subprocess.CalledProcessError as e:
            print(e.output.decode("utf-8"))
            raise

    def assert_certificate_in_cacert(self, cert_alias):
        env = dict(os.environ)
        output = self.cmd(
            (
                "cf",
                "ssh",
                self.app_name,
                "-c",
                "app/.local/usr/lib/jvm/*/bin/keytool -list -storepass changeit -keystore app/.local/usr/lib/jvm/*/lib/security/cacerts",  # noqa: E501
            ),
            env=env,
        )
        self.assertIn(cert_alias, output)

    def bytes(self, s):
        return s.encode("utf-8")

    def query_mxadmin(self, command):
        basic_auth = "MxAdmin:{}".format(self.mx_password)
        basic_auth_base64 = b64encode(self.bytes(basic_auth)).decode("utf-8")
        m2ee_auth_base64 = b64encode(self.bytes(self.mx_password)).decode(
            "utf-8"
        )

        return requests.post(
            "https://{}/_mxadmin/".format(self.app_name),
            data=json.dumps(command),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Basic {}".format(basic_auth_base64),
                "X-M2EE-Authentication": m2ee_auth_base64,
            },
            timeout=15,
        )
