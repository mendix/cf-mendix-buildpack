import os
import json
import subprocess
import unittest
import uuid
import requests


class BaseTest(unittest.TestCase):
    _multiprocess_can_split_ = True

    '''
    BaseTest class provides initialization and teardown functionality
    for mendix buildpack tests that utilize cloudfoundry
    '''

    def __init__(self, *args, **kwargs):
        super(BaseTest, self).__init__(*args, **kwargs)
        if not os.environ.get("TRAVIS_BRANCH"):
            current_branch = subprocess.check_output("git rev-parse --symbolic-full-name --abbrev-ref HEAD", shell=True)
        else:
            current_branch = "master"
        self.cf_domain = os.environ.get("CF_DOMAIN")
        assert self.cf_domain
        self.branch_name = os.environ.get("TRAVIS_BRANCH", current_branch)
        self.mx_password = os.environ.get("MX_PASSWORD", "Y0l0lop13#123")

    def startApp(self):
        try:
            subprocess.check_call(('cf', 'start', self.app_name))
        except subprocess.CalledProcessError as e:
            print(self.get_recent_logs())
            raise e

    def setUpCF(self, package_name, env_vars=None):
        subdomain = "ops-" + str(uuid.uuid4()).split("-")[0]
        self.app_name = "{name}.{domain}".format(name=subdomain, domain=self.cf_domain)
        self.package_name = package_name
        self.package_url = os.environ.get(
            "PACKAGE_URL",
            "https://s3-eu-west-1.amazonaws.com/mx-ci-binaries/" + package_name
        )

        subprocess.check_call((
            'wget', '--quiet', '-c',
            '-O', self.package_name,
            self.package_url,
        ))
        subprocess.check_call((
            'cf', 'push', self.app_name,
            '-d', self.cf_domain,
            '-p', self.package_name,
            '-n', subdomain,
            '--no-start',
            '-k', '3G',
            '-m', '2G',
            '-b', 'https://github.com/mendix/cf-mendix-buildpack.git#%s' % self.branch_name,
        ))
        subprocess.check_call(('./create-app.sh', self.app_name))

        app_guid = subprocess.check_output(('cf', 'app', self.app_name, '--guid')).strip()

        environment = {
            'ADMIN_PASSWORD': self.mx_password,
            'DEBUGGER_PASSWORD': self.mx_password,
            'DEVELOPMENT_MODE': 'true',
            'S3_USE_SSE': 'true',
            'USE_DATA_SNAPSHOT': 'true',
        }

        if env_vars is not None:
            environment.update(env_vars)

        subprocess.check_call((
            'cf', 'curl', '-X', 'PUT',
            '/v2/apps/%s' % app_guid,
            '-d', json.dumps({"environment_json": environment})
        ))

    def tearDown(self):
        cmds = [
            "cf stop \"%s\"" % self.app_name,
            "cf delete \"%s\" -f -r" % self.app_name,
            "cf delete-service \"%s-database\" -f" % self.app_name,
            "cf delete-service \"%s-storage\" -f" % self.app_name,
            "cf delete-service \"%s-schnapps\" -f" % self.app_name
        ]
        for cmd in cmds:
            subprocess.check_call(cmd, shell=True)

    def assert_app_running(self, app_name, path="/xas/", code=401):
        full_uri = "https://" + app_name + path
        r = requests.get(full_uri)
        assert r.status_code == code

    def get_recent_logs(self):
        return unicode(subprocess.check_output(('cf', 'logs', self.app_name, '--recent')), 'utf-8')

    def assert_string_in_recent_logs(self, app_name, substring):
        output = subprocess.check_output(('cf', 'logs', app_name, '--recent'))
        if output.find(substring) > 0:
            pass
        else:
            print(output)
            self.fail('Failed to find substring in recent logs: ' + substring)
