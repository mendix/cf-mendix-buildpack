#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

from base64 import b64encode
import socket
from .log import logger

try:
    import httplib2
except ImportError:
    logger.critical(
        "Failed to import httplib2. This module is needed by "
        "m2ee. Please povide it on the python library path"
    )
    raise

# Use json if available. If not (python 2.5) we need to import
# the simplejson module instead, which has to be available.
try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError as ie:
        logger.critical(
            "Failed to import json as well as simplejson. If "
            "using python 2.5, you need to provide the simplejson "
            "module in your python library path."
        )
        raise


class M2EEClient:
    def __init__(self, url, password):
        self._url = url
        self._headers = {
            "Content-Type": "application/json",
            "X-M2EE-Authentication": b64encode(
                password.encode("utf-8")
            ).decode("ascii"),
        }

    def request(self, action, params=None, timeout=None):
        body = {"action": action}
        if params:
            body["params"] = params
        body = json.dumps(body)
        h = httplib2.Http(
            timeout=timeout, proxy_info=None
        )  # httplib does not like os.fork
        logger.trace("M2EE request body: %s" % body)
        (response_headers, response_body) = h.request(
            self._url, "POST", body, headers=self._headers
        )
        if response_headers["status"] == "200":
            logger.trace("M2EE response: %s" % response_body)
            return M2EEResponse(
                action, json.loads(response_body.decode("utf-8"))
            )
        else:
            logger.error(
                "non-200 http status code: %s %s"
                % (response_headers, response_body)
            )

    def ping(self, timeout=5):
        try:
            response = self.request("echo", {"echo": "ping"}, timeout)
            if response.get_result() == 0:
                return True
        except AttributeError as e:
            # httplib 0.6 throws AttributeError: 'NoneType' object has no
            # attribute 'makefile' in case of a connection refused :-|
            logger.trace("Got %s: %s" % (type(e), e))
        except (socket.error, socket.timeout) as e:
            logger.trace("Got %s: %s" % (type(e), e))
        except Exception as e:
            logger.error("Got %s: %s" % (type(e), e))
            import traceback

            logger.error(traceback.format_exc())
        return False

    def echo(self, params=None):
        myparams = {"echo": "ping"}
        if params is not None:
            myparams.update(params)
        return self.request("echo", myparams, timeout=10)

    def get_critical_log_messages(self):
        echo_feedback = self.echo().get_feedback()
        if echo_feedback["echo"] != "pong":
            errors = echo_feedback["errors"]
            # default to 3.0 format [{"message":"Hello,
            # world!","timestamp":1315316488958,"cause":""}, ...]
            if type(errors[0]) != dict:
                return errors
            from datetime import datetime

            result = []
            for error in errors:
                errorline = []
                if "message" in error and error["message"] != "":
                    errorline.append("- %s" % error["message"])
                if "cause" in error and error["cause"] != "":
                    errorline.append("- Caused by: %s" % error["cause"])
                if len(errorline) == 0:
                    errorline.append("- [No message or cause was logged]")
                errorline.insert(
                    0,
                    datetime.fromtimestamp(error["timestamp"] / 1000).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                )
                result.append(" ".join(errorline))
            return result
        return []

    def shutdown(self, timeout=5):
        # currently, the exception thrown is a feature, because the shutdown
        # action gets interrupted while executing
        try:
            self.request("shutdown", timeout=timeout)
        except Exception:
            return True
        return False

    def close_stdio(self):
        return self.request("close_stdio")

    def runtime_status(self):
        return self.request("runtime_status", timeout=10)

    def runtime_statistics(self):
        return self.request("runtime_statistics", timeout=10)

    def server_statistics(self):
        return self.request("server_statistics", timeout=10)

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

    def get_profiler_logs(self):
        return self.request("get_profiler_logs")

    def start_profiler(
        self, minimum_duration_to_log=None, flush_interval=None
    ):
        params = {}
        if minimum_duration_to_log is not None:
            params["minimum_duration_to_log"] = minimum_duration_to_log

        if flush_interval is not None:
            params["flush_interval"] = flush_interval

        return self.request("start_profiler", params)

    def stop_profiler(self):
        return self.request("stop_profiler")

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


class M2EEResponse:

    ERR_REQUEST_NULL = -1
    ERR_CONTENT_TYPE = -2
    ERR_HTTP_METHOD = -3
    ERR_FORBIDDEN = -4
    ERR_ACTION_NOT_FOUND = -5
    ERR_READ_REQUEST = -6
    ERR_WRITE_REQUEST = -7

    def __init__(self, action, json):
        self._action = action
        self._json = json
        self._result = self._json["result"]
        self._feedback = self._json.get("feedback", {})
        self._message = self._json.get("message", None)
        self._cause = self._json.get("cause", None)
        self._stacktrace = self._json.get("stacktrace", None)

    def get_result(self):
        return self._result

    def get_feedback(self):
        return self._feedback

    def get_message(self):
        return self._message

    def get_cause(self):
        return self._cause

    def get_stacktrace(self):
        return self._stacktrace

    def has_error(self):
        return self._result != 0

    def display_error(self):
        if self.has_error():
            logger.error(self.get_error())
            if self._stacktrace:
                logger.debug(self._stacktrace)

    def get_error(self):
        error = "Executing %s did not succeed: result: %s, message: %s" % (
            self._action,
            self._json["result"],
            self._json["message"],
        )
        if self._json.get("cause", None) is not None:
            error = "%s, caused by: %s" % (error, self._json["cause"])
        return error

    def __str__(self):
        return str({"action": self._action, "json": self._json})
