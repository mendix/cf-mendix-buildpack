import cgi
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urljoin

import requests

import buildpackutil
import mxbuild
from m2ee import logger

ROOT_DIR = os.getcwd() + "/"
MXBUILD_FOLDER = ROOT_DIR + "mxbuild/"


PROJECT_DIR = ".local/project"
DEPLOYMENT_DIR = os.path.join(PROJECT_DIR, "deployment")
INCOMING_MPK_DIR = ".local/tmp_project"
INTERMEDIATE_MPK_DIR = ".local/tmp_project_2"
MPK_FILE = os.path.join(PROJECT_DIR, "app.mpk")

INSTADEPLOY_FEEDBACK_PATH = "api/1/environments/{app_id}/instadeployfeedback"

for directory in (
    MXBUILD_FOLDER,
    PROJECT_DIR,
    DEPLOYMENT_DIR,
    INCOMING_MPK_DIR,
    INTERMEDIATE_MPK_DIR,
):
    buildpackutil.mkdir_p(directory)


class MxBuildFailure(Exception):
    """
    Represents any 4xx 5xx issues retrieved from MxBuild HTTP Server
    """

    def __init__(self, message, status_code, mxbuild_response):
        super().__init__(message)
        self.status_code = status_code
        self.mxbuild_response = mxbuild_response


class InstaDeployThread(threading.Thread):
    """
    The reference for this implementation can be found at
    'https://docs.mendix.com/refguide/mxbuild'
    """

    def __init__(self, port, restart_callback, reload_callback, mx_version):
        super().__init__()
        self.port = port
        self.restart_callback = restart_callback
        self.reload_callback = reload_callback
        self.mx_version = mx_version

    def run(self):
        logger.debug("Going to start mxbuild in serve mode")
        mxbuild.start_mxbuild_server(
            os.path.join(os.getcwd(), ".local"), self.mx_version
        )
        time.sleep(10)
        logger.debug("Listening on port %d for MPK uploads" % int(self.port))
        server = HTTPServer(("", self.port), MPKUploadHandler)
        server.restart_callback = self.restart_callback
        server.reload_callback = self.reload_callback
        server.serve_forever()


class MyFieldStorage(cgi.FieldStorage):
    # cgi bug, see https://stackoverflow.com/questions/42213318
    @property
    def filename(self):
        if self._original_filename is not None:
            return self._original_filename
        elif self.name == "file":
            return "file_name"
        else:
            return None

    @filename.setter
    def filename(self, value):
        self._original_filename = value


class MPKUploadHandler(BaseHTTPRequestHandler):
    def process_request(self):
        try:
            form = MyFieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers["Content-Type"],
                },
            )
            if "file" in form:
                with open(MPK_FILE, "wb") as output:
                    shutil.copyfileobj(form["file"].file, output)
                update_project_dir()
                mxbuild_response = build()
                logger.debug(mxbuild_response)
                if mxbuild_response["status"] == "Busy":
                    return (200, {"state": "BUSY"}, mxbuild_response)
                if mxbuild_response["status"] != "Success":
                    # possible 'status': Success, Failure, Busy
                    logger.warning(
                        "Failed to build project, "
                        "keeping previous model running"
                    )
                    state = "FAILED"
                elif mxbuild_response["restartRequired"] is True:
                    logger.info("Restarting app after MPK push")
                    self.server.restart_callback()
                    state = "STARTED"
                else:
                    logger.info("Reloading model after MPK push")
                    self.server.reload_callback()
                    state = "STARTED"
                return (200, {"state": state}, mxbuild_response)
            else:
                return (
                    401,
                    {"state": "FAILED", "errordetails": "No MPK found"},
                    None,
                )

        except MxBuildFailure as mbf:
            logger.warning(
                "InstaDeploy terminating with MxBuildFailure: {}".format(
                    mbf.message
                )
            )
            return (200, {"state": "FAILED"}, mbf.mxbuild_response)

        except Exception:
            logger.warning("Instadeploy failed", exc_info=True)
            return (
                500,
                {"state": "FAILED", "errordetails": traceback.format_exc()},
                None,
            )

    def do_POST(self):
        status_code, data, mxbuild_response = self.process_request()
        if mxbuild_response:
            flat_response = extract_mxbuild_response(mxbuild_response)
            data.update(flat_response)
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        data["code"] = status_code
        self.wfile.write(json.dumps(data).encode("utf-8"))


def update_project_dir():
    logger.debug("unzipping " + MPK_FILE + " to " + INCOMING_MPK_DIR)
    subprocess.check_call(("rm", "-rf", INCOMING_MPK_DIR))
    buildpackutil.mkdir_p(INCOMING_MPK_DIR)
    subprocess.check_call(("unzip", "-oqq", MPK_FILE, "-d", INCOMING_MPK_DIR))
    new_mpr = os.path.basename(
        buildpackutil.get_mpr_file_from_dir(INCOMING_MPK_DIR)
    )
    existing_mpr_path = buildpackutil.get_mpr_file_from_dir(PROJECT_DIR)
    if existing_mpr_path:
        existing_mpr = os.path.basename(existing_mpr_path)
    else:
        existing_mpr = None
    logger.debug("rsync from incoming to intermediate")
    if buildpackutil.get_buildpack_loglevel() < logging.INFO:
        quiet_or_verbose = "--verbose"
    else:
        quiet_or_verbose = "--quiet"
    subprocess.call(
        (
            "rsync",
            "--recursive",
            "--checksum",
            "--delete",
            INCOMING_MPK_DIR + "/",
            INTERMEDIATE_MPK_DIR + "/",
        )
    )
    logger.debug("rsync from intermediate to project")
    if new_mpr == existing_mpr:
        update_or_delete = "--update"
    else:
        update_or_delete = "--delete"

    subprocess.call(
        (
            "rsync",
            "--recursive",
            update_or_delete,
            quiet_or_verbose,
            INTERMEDIATE_MPK_DIR + "/",
            PROJECT_DIR + "/",
        )
    )


def build():
    mpr = os.path.abspath(buildpackutil.get_mpr_file_from_dir(PROJECT_DIR))
    response = requests.post(
        "http://localhost:6666/build",
        data=json.dumps(
            {
                "target": "Deploy",
                "projectFilePath": mpr,
                "forceFullDeployment": False,
            }
        ),
        headers={"Content-Type": "application/json"},
        timeout=120,
    )

    if response.status_code != requests.codes.ok:
        raise MxBuildFailure(
            "MxBuild failure", response.status_code, response.json()
        )

    result = response.json()
    if result["status"] == "Success":
        try:
            sync_project_files()
            logger.info("Syncing project files ...")
        except Exception:
            logger.warning(
                "Syncing project files failed: %s", traceback.format_exc()
            )
            raise
        try:
            send_metadata_to_cloudportal()
        except Exception:
            logger.warning(
                "Failed to send instadeploy feedback to Cloud Portal",
                exc_info=True,
            )
    else:
        logger.warning("Not syncing project files. MxBuild result: %s", result)

    return result


def sync_project_files():
    sync_folders = ["web", "model"]
    # check for mx8 native folder, copy that as well
    if os.path.exists(os.path.join(DEPLOYMENT_DIR, "native")):
        sync_folders.append("native")

    for name in sync_folders:
        subprocess.check_call(
            (
                "rsync",
                "-a",
                os.path.join(DEPLOYMENT_DIR, name) + "/",
                os.path.join(ROOT_DIR, name) + "/",
            )
        )


def extract_mxbuild_response(mxbuild_response):
    r = {}
    if "problems" in mxbuild_response:
        r["buildstatus"] = json.dumps(mxbuild_response["problems"])
    # When there're consistency errors, the problems field
    # does not necessarily include details and there is only
    # a high-level message
    if "message" in mxbuild_response:
        r["message"] = mxbuild_response["message"]
    return r


def send_metadata_to_cloudportal():
    required_variables = ("CLOUD_PORTAL_LOCATION", "ENVIRONMENT_SIGNATURE")

    if not all([v in os.environ for v in required_variables]):
        logger.info(
            "Required environment variables for intadeploy feedback "
            "are missing. Skipping instadeploy feedback."
        )
        return

    app_id = json.loads(os.environ["VCAP_APPLICATION"])["name"]
    target_path = INSTADEPLOY_FEEDBACK_PATH.format(app_id=app_id)
    target_url = urljoin(os.environ["CLOUD_PORTAL_LOCATION"], target_path)

    with open("/home/vcap/app/model/metadata.json", "rb") as metadata_json:
        files = {"file": metadata_json}
        headers = {
            "Mendix-Environment-Signature": os.environ["ENVIRONMENT_SIGNATURE"]
        }
        # We don't care about the response.
        requests.post(target_url, files=files, headers=headers)
        logger.info("Updated metadata in CloudPortal")
