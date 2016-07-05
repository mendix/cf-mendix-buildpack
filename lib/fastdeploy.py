from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import cgi
import json
import shutil
import mxbuild
import os
from m2ee import logger
import traceback
import threading
import buildpackutil
import requests
import subprocess


ROOT_DIR = os.getcwd() + '/'
MXBUILD_FOLDER = ROOT_DIR + 'mxbuild/'


PROJECT_DIR = '.local/project'
DEPLOYMENT_DIR = os.path.join(PROJECT_DIR, 'deployment')
INCOMING_MPK_DIR = '.local/tmp_project'
INTERMEDIATE_MPK_DIR = '.local/tmp_project_2'
MPK_FILE = os.path.join(PROJECT_DIR, 'app.mpk')

for directory in (
    MXBUILD_FOLDER,
    PROJECT_DIR,
    DEPLOYMENT_DIR,
    INCOMING_MPK_DIR,
    INTERMEDIATE_MPK_DIR
):
    buildpackutil.mkdir_p(directory)


class FastDeployThread(threading.Thread):

    def __init__(self, port, restart_callback, reload_callback, mx_version):
        super(FastDeployThread, self).__init__()
        self.daemon = True
        self.port = port
        self.restart_callback = restart_callback
        self.reload_callback = reload_callback
        self.mx_version = mx_version

    def run(self):
        logger.debug('Going to start mxbuild in serve mode')
        mxbuild.start_mxbuild_server(
            os.path.join(os.getcwd(), '.local'),
            os.path.join(os.getcwd(), 'lib', 'mono-lib'),
            self.mx_version,
        )
        logger.debug('Listening on port %d for MPK uploads' % int(self.port))
        server = HTTPServer(('', self.port), MPKUploadHandler)
        server.restart_callback = self.restart_callback
        server.reload_callback = self.reload_callback
        server.serve_forever()


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
                with open(MPK_FILE, 'wb') as output:
                    shutil.copyfileobj(form['file'].file, output)
                mxbuild_response = build()
                if mxbuild_response['restartRequired'] is True:
                    logger.info('Restarting app after MPK push')
                    self.server.restart_callback()
                else:
                    logger.info('Reloading model after MPK push')
                    self.server.reload_callback()
                return self._terminate(200, {
                    'state': 'STARTED',
                }, mxbuild_response)
            else:
                return self._terminate(401, {
                    'state': 'FAILED',
                    'errordetails': 'No MPK found',
                })
        except Exception:
            return self._terminate(500, {
                'state': 'FAILED',
                'errordetails': traceback.format_exc(),
            })

    def _terminate(self, status_code, data, mxbuild_response=None):
        if mxbuild_response and 'problems' in mxbuild_response:
            data['buildstatus'] = json.dumps(mxbuild_response['problems'])
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        data['code'] = status_code
        self.wfile.write(json.dumps(data))


def build():
    logger.debug('unzipping ' + MPK_FILE + ' to ' + INCOMING_MPK_DIR)
    subprocess.check_call(('unzip', '-oqq', MPK_FILE, '-d', INCOMING_MPK_DIR))
    logger.debug('rsync from incoming to intermediate')
    subprocess.call((
        'rsync', '--recursive', '--checksum',
        INCOMING_MPK_DIR + '/',
        INTERMEDIATE_MPK_DIR + '/',
    ))
    logger.debug('rsync from intermediate to project')
    subprocess.call((
        'rsync', '--recursive', '--update',
        INTERMEDIATE_MPK_DIR + '/',
        PROJECT_DIR + '/',
    ))
    mpr = os.path.abspath(buildpackutil.get_mpr_file_from_dir(PROJECT_DIR))
    response = requests.post(
        'http://localhost:6666/build',
        data=json.dumps({
            'target': 'Deploy',
            'projectFilePath': mpr,
            'forceFullDeployment': False
        }),
        headers={'Content-Type': 'application/json'},
        timeout=120,
    )
    response.raise_for_status()

    for name in ('web', 'model'):
        subprocess.call((
            'rsync', '-a',
            os.path.join(DEPLOYMENT_DIR, name) + '/',
            os.path.join(ROOT_DIR, name) + '/',
        ))

    return response.json()
