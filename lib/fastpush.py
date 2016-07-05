from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import cgi
import json
import mxbuild
import os
from m2ee import logger
import traceback
import threading
import buildpackutil
import requests


ROOT_DIR = os.getcwd() + '/'
MXBUILD_FOLDER = ROOT_DIR + 'mxbuild/'


PROJECT_DIR = '.local/project'
DEPLOYMENT_DIR = os.path.join(PROJECT_DIR, 'deployment')
TMP_PROJECT_DIR = '.local/tmp_project'
TMP2_PROJECT_DIR = '.local/tmp_project_2'
MPK_FILE = os.path.join(PROJECT_DIR, 'app.mpk')

for directory in (
    MXBUILD_FOLDER,
    PROJECT_DIR,
    TMP_PROJECT_DIR,
    DEPLOYMENT_DIR,
    TMP2_PROJECT_DIR
):
    buildpackutil.mkdir_p(directory)


class FastPushThread(threading.Thread):

    def __init__(self, port, restart_callback, reload_callback, mx_version):
        super(FastPushThread, self).__init__()
        self.daemon = True
        self.port = port
        self.restart_callback = restart_callback
        self.reload_callback = reload_callback
        self.mx_version = mx_version

    def run(self):
        do_run(
            self.port,
            self.restart_callback,
            self.reload_callback,
            self.mx_version,
        )


class MPKUploadHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': self.headers['Content-Type'],
                })
            if 'file' in form:
                data = form['file'].file.read()
                open(MPK_FILE, 'wb').write(data)
                mxbuild_response = build()
                if 'restartRequired' in str(mxbuild_response):
                    logger.info(str(mxbuild_response))
                    logger.info('Restarting app, reloading for now')
#                    self.server.mxbuild_restart_callback()
                    self.server.mxbuild_reload_callback()
                else:
                    logger.info(str(mxbuild_response))
                    logger.info('Reloading model')
                    self.server.mxbuild_reload_callback()
                return self._terminate(200, {
                    'state': 'STARTED',
                }, mxbuild_response)
            else:
                return self._terminate(401, {
                    'state': 'FAILED',
                    'errordetails': 'No MPK found',
                })
        except Exception:
            details = traceback.format_exc()
            return self._terminate(500, {
                'state': 'FAILED',
                'errordetails': details,
            })

    def _terminate(self, status_code, data, mxbuild_response=None):
        if mxbuild_response and 'problems' in mxbuild_response:
            data['buildstatus'] = json.dumps(mxbuild_response['problems'])
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        data['code'] = status_code
        self.wfile.write(json.dumps(data))


def do_run(port, restart_callback, reload_callback, mx_version):
    mxbuild.start_mxbuild_server(
        os.path.join(os.getcwd(), '.local'),
        os.path.join(os.getcwd(), 'lib', 'mono-lib'),
        mx_version,
    )

    print('Going to listen on port ', port)
    server = HTTPServer(('', port), MPKUploadHandler)
    server.mxbuild_restart_callback = restart_callback
    server.mxbuild_reload_callback = reload_callback
    server.serve_forever()
