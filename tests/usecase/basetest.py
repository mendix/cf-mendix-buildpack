import os
import subprocess
import unittest
import uuid
import requests


class BaseTest(unittest.TestCase):
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

    def setUpCF(self, package_name):
        subdomain = "ops-" + str(uuid.uuid4()).split("-")[0]
        self.app_name = "{name}.{domain}".format(name=subdomain, domain=self.cf_domain)
        self.package_name = package_name
        self.package_url = os.environ.get(
            "PACKAGE_URL",
            "https://s3-eu-west-1.amazonaws.com/mx-ci-binaries/" + package_name)

        cmds = [
            "wget -O \"%s\" \"%s\"" % (self.package_name, self.package_url),
            "cf push -p %s -n %s %s --no-start -b https://github.com/mendix/cf-mendix-buildpack.git#%s" % (self.package_name, subdomain, self.app_name, self.branch_name),
            "cf create-service schnapps basic \"%s-schnapps\"" % self.app_name,
            "cf create-service PostgreSQL \"Basic PostgreSQL Plan\" \"%s-database\"" % self.app_name,
            "cf create-service amazon-s3 shared \"%s-storage\"" % self.app_name,
            "cf bind-service \"%s\" \"%s-schnapps\"" % (self.app_name, self.app_name),
            "cf bind-service \"%s\" \"%s-storage\"" % (self.app_name, self.app_name),
            "cf bind-service \"%s\" \"%s-database\"" % (self.app_name, self.app_name),
            "cf set-env \"%s\" ADMIN_PASSWORD \"%s\"" % (self.app_name, self.mx_password),
            "cf set-env \"%s\" DEBUGGER_PASSWORD \"%s\"" % (self.app_name, self.mx_password),
            "cf set-env \"%s\" DEVELOPMENT_MODE \"true\"" % self.app_name,
            "cf set-env \"%s\" S3_USE_SSE \"true\"" % self.app_name,
            "cf set-env \"%s\" USE_DATA_SNAPSHOT \"true\"" % self.app_name,
        ]
        for cmd in cmds:
            subprocess.check_call(cmd, shell=True)

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
