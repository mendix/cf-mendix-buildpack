#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

from base64 import b64encode
import json
import logging
import socket
from version import MXVersion

logger = logging.getLogger(__name__)

try:
    import httplib2
except ImportError:
    logger.critical("Failed to import httplib2. This module is needed by "
                    "m2ee. Please povide it on the python library path")
    raise


class M2EEClient:

    def __init__(self, url, password):
        self._url = url
        self._headers = {
            'Content-Type': 'application/json',
            'X-M2EE-Authentication': b64encode(password),
            'Connection': 'close',
        }

    def request(self, action, params=None, timeout=None):
        body = {"action": action}
        if params:
            body["params"] = params
        body = json.dumps(body)
        try:
            h = httplib2.Http(timeout=timeout)  # httplib does not like os.fork
            logger.trace("M2EE request body: %s" % body)
            (response_headers, response_body) = h.request(self._url, "POST", body,
                                                          headers=self._headers)
            logger.trace("M2EE response: %s" % response_body)
            if (response_headers['status'] != "200"):
                raise M2EEAdminHTTPException("Non OK http status code: %s %s" %
                                             (response_headers, response_body))
            response = json.loads(response_body)
            if response['result'] != 0:
                raise M2EEAdminException(action, response)
            return response.get('feedback', {})
        except AttributeError, e:
            # httplib 0.6 throws this in case of a connection refused :-|
            if str(e) == "'NoneType' object has no attribute 'makefile'":
                message = "Admin API not available for requests."
                logger.trace("%s (%s: %s)" % (message, type(e), e))
                raise M2EEAdminNotAvailable(message)
            raise e
        except (socket.error, socket.timeout), e:
            message = "Admin API not available for requests: (%s: %s)" % (type(e), e)
            logger.trace(message)
            raise M2EEAdminNotAvailable(message)

    def ping(self, timeout=5):
        try:
            self.echo(timeout=timeout)
            return True
        except (M2EEAdminException, M2EEAdminHTTPException, M2EEAdminNotAvailable):
            return False

    def echo(self, params=None, timeout=5):
        myparams = {"echo": "ping"}
        if params is not None:
            myparams.update(params)
        return self.request("echo", myparams, timeout)

    def require_action(self, action):
        try:
            feedback = self.get_admin_action_info()
            implemented = action in feedback['action_info']
        except M2EEAdminException as e:
            if e.result == M2EEAdminException.ERR_ACTION_NOT_FOUND:
                if action in M2EEAdminException.implemented_in:
                    implemented_in = M2EEAdminException.implemented_in[action]
                    runtime_version = MXVersion(self.about()['version'])
                    implemented = runtime_version >= implemented_in
                else:
                    implemented = True
            else:
                raise
        if implemented is False:
            raise M2EEAdminException(
                action,
                {"result": M2EEAdminException.ERR_ACTION_NOT_FOUND}
            )

    def get_admin_action_info(self):
        return self.request("get_admin_action_info")

    def get_critical_log_messages(self):
        echo_feedback = self.echo()
        if echo_feedback['echo'] != "pong":
            errors = echo_feedback['errors']
            # default to 3.0 format [{"message":"Hello,
            # world!","timestamp":1315316488958,"cause":""}, ...]
            if type(errors[0]) != dict:
                return errors
            from datetime import datetime
            result = []
            for error in errors:
                errorline = []
                if 'message' in error and error['message'] != '':
                    errorline.append("- %s" % error['message'])
                if 'cause' in error and error['cause'] != '':
                    errorline.append("- Caused by: %s" % error['cause'])
                if len(errorline) == 0:
                    errorline.append("- [No message or cause was logged]")
                errorline.insert(
                    0,
                    datetime.fromtimestamp(error['timestamp'] / 1000)
                    .strftime("%Y-%m-%d %H:%M:%S")
                )
                result.append(' '.join(errorline))
            return result
        return []

    def shutdown(self, timeout=5):
        # Currently, the exception thrown is a feature, because the shutdown
        # action gets interrupted while executing. Even if an internal error
        # occurs in the runtime / appcontainer there's no point in trying to
        # handle it, if it would show up here, since there's an unforgiving
        # System.exit(0); in the finally clause of the shutdown action. ;-)
        try:
            self.request("shutdown", timeout=timeout)
        except Exception:
            pass

    def close_stdio(self):
        return self.request("close_stdio")

    def runtime_status(self):
        return self.request("runtime_status")

    def runtime_statistics(self, timeout=None):
        return self.request("runtime_statistics", timeout=timeout)

    def server_statistics(self, timeout=None):
        return self.request("server_statistics", timeout=timeout)

    def create_log_subscriber(self, params):
        return self.request("create_log_subscriber", params)

    def start_logging(self):
        return self.request("start_logging")

    def update_configuration(self, params):
        return self.request("update_configuration", params)

    def update_custom_configuration(self, params):
        return self.request("update_custom_configuration", params)

    def update_appcontainer_configuration(self, params):
        return self.request("update_appcontainer_configuration", params)

    def start(self, params=None):
        return self.request("start", params)

    def get_ddl_commands(self, params=None):
        return self.request("get_ddl_commands", params)

    def execute_ddl_commands(self, params=None):
        return self.request("execute_ddl_commands", params)

    def update_admin_user(self, params):
        return self.request("update_admin_user", params)

    def create_admin_user(self, params):
        return self.request("create_admin_user", params)

    def get_logged_in_user_names(self, params=None):
        return self.request("get_logged_in_user_names", params)

    def set_jetty_options(self, params=None):
        return self.request("set_jetty_options", params)

    def add_mime_type(self, params):
        return self.request("add_mime_type", params)

    def about(self):
        return self.request("about")

    def set_log_level(self, params):
        return self.request("set_log_level", params)

    def get_log_settings(self, params):
        return self.request("get_log_settings", params)

    def check_health(self, params=None):
        return self.request("check_health", params)

    def get_current_runtime_requests(self):
        return self.request("get_current_runtime_requests")

    def interrupt_request(self, params):
        return self.request("interrupt_request", params)

    def get_all_thread_stack_traces(self):
        return self.request("get_all_thread_stack_traces")

    def get_license_information(self):
        return self.request("get_license_information")

    def set_license(self, params):
        return self.request("set_license", params)

    def connect_xmpp(self, params):
        return self.request("connect_xmpp", params)

    def disconnect_xmpp(self):
        return self.request("disconnect_xmpp")

    def create_runtime(self, params):
        return self.request("createruntime", params)

    def enable_debugger(self, params):
        return self.request("enable_debugger", params)

    def disable_debugger(self):
        return self.request("disable_debugger")

    def get_debugger_status(self):
        return self.request("get_debugger_status")

    def cache_statistics(self):
        return self.request("cache_statistics")


class M2EEAdminHTTPException(Exception):
    pass


class M2EEAdminNotAvailable(Exception):
    pass


class M2EEAdminException(Exception):

    ERR_REQUEST_NULL = -1
    ERR_CONTENT_TYPE = -2
    ERR_HTTP_METHOD = -3
    ERR_FORBIDDEN = -4
    ERR_ACTION_NOT_FOUND = -5
    ERR_READ_REQUEST = -6
    ERR_WRITE_REQUEST = -7

    implemented_in = {
        "get_admin_action_info": '3',
        "check_health": '2.5.4',
        "cache_statistics": '4',
        "get_license_information": '3',
        "set_license": '3',
        "enable_debugger": '4.3',
        "disable_debugger": '4.3',
        "get_debugger_status": '4.3',
        "get_current_runtime_requests": ('2.5.8', '3.1'),
        "interrupt_request": ('2.5.8', '3.1'),
        "get_all_thread_stack_traces": '3.2',
    }

    def __init__(self, action, json):
        self.action = action
        self.json = json
        self.result = json['result']
        self.feedback = json.get('feedback', {})
        self.message = json.get('message', None)
        self.cause = json.get('cause', None)
        self.stacktrace = json.get('stacktrace', None)

    def __str__(self):
        if ((self.result == M2EEAdminException.ERR_ACTION_NOT_FOUND
             and self.action in M2EEAdminException.implemented_in)):
            avail_since = M2EEAdminException.implemented_in[self.action]
            if isinstance(avail_since, tuple):
                if len(avail_since) > 2:
                    implemented_in_msg = (
                        '%s, %s and %s' %
                        (
                            ', '.join(map(str, avail_since[:-2])),
                            avail_since[-2], avail_since[-1]
                        )
                    )
                else:
                    implemented_in_msg = '%s and %s' % avail_since
            else:
                implemented_in_msg = avail_since
            return ("This action is not available in the Mendix Runtime "
                    "version you are currently using. It was implemented "
                    "in Mendix %s" % implemented_in_msg)
        else:
            error = "Executing %s did not succeed: result: %s, message: %s" % (
                self.action, self.result, self.message)
            if self.cause is not None:
                error = "%s, caused by: %s" % (error, self.cause)
            return error
