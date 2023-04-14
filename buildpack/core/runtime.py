import atexit
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import time

import backoff
from buildpack import util
from lib.m2ee import M2EE as m2ee_class
from lib.m2ee.version import MXVersion

from . import security

BASE_PATH = os.getcwd()

from lib.m2ee import logger  # noqa: E402

logger.setLevel(util.get_buildpack_loglevel())

# Disable duplicate log lines for M2EE
handlers = logging.getLogger("m2ee").handlers
if len(handlers) > 2:
    logging.getLogger("m2ee").handlers = handlers[:2]
logging.getLogger("m2ee").propagate = False


def is_version_implemented(version):
    return bool(version.major >= 6)


def is_version_supported(version):
    # Support for the latest three major versions:
    # https://docs.mendix.com/releasenotes/studio-pro/lts-mts
    return bool(version.major >= 7)


def is_version_maintained(version):
    # LTS / MTS versions: https://docs.mendix.com/releasenotes/studio-pro/lts-mts
    if version.major == 7 and version.minor == 23:
        return True
    if version.major == 8 and version.minor == 18:
        return True
    if version.major == 9 and version.minor == 6:
        return True
    if version.major == 9 and version.minor == 12:
        return True
    if version.major == 9 and version.minor == 18:
        return True
    if version.major == 9 and version.minor == 24:
        return True
    return False


def stage(buildpack_dir, build_path, cache_path):
    logging.debug("Creating directory structure for Mendix runtime...")
    for name in ["runtimes", "log", "database", "data", "bin"]:
        util.mkdir_p(os.path.join(build_path, name))
    for name in ["files", "tmp", "database"]:
        util.mkdir_p(os.path.join(build_path, "data", name))

    logging.debug("Staging the Mendix runtime...")
    shutil.copy(
        os.path.join(buildpack_dir, "etc", "m2ee", "m2ee.yaml"),
        os.path.join(build_path, ".local", "m2ee.yaml"),
    )
    resolve_runtime_dependency(buildpack_dir, build_path, cache_path)


FORCED_MXRUNTIME_URL_KEY = "FORCED_MXRUNTIME_URL"


def resolve_runtime_dependency(
    buildpack_dir,
    build_dir,
    cache_dir,
    destination=None,
    prefix="mendix",
):
    url = os.getenv(FORCED_MXRUNTIME_URL_KEY, util.get_blobstore())
    if url.endswith("/"):
        url = url[:-1]
    if not destination:
        destination = os.path.join(build_dir, "runtimes")
    util.resolve_dependency(
        f"mendix.runtime.{prefix}",
        destination,
        buildpack_dir=buildpack_dir,
        cache_dir=cache_dir,
        ignore_cache=FORCED_MXRUNTIME_URL_KEY in os.environ,
        overrides={
            "version": str(get_runtime_version(build_dir)),
            "url": url,
        },
    )


def get_metadata_value(key, build_path=BASE_PATH):
    file_name = os.path.join(build_path, "model", "metadata.json")
    try:
        with open(file_name) as file_handle:
            data = json.loads(file_handle.read())
            return data[key]
    except IOError:
        return None


def get_runtime_version(build_path=BASE_PATH):
    result = get_metadata_value("RuntimeVersion", build_path)
    if result is None:
        logging.debug(
            "Cannot retrieve runtime version %s from metadata file, "
            "falling back to project file",
            result,
        )
        mpr = util.get_mpr_file_from_dir(build_path)
        if not mpr:
            raise Exception("No model/metadata.json or .mpr found in archive")

        cursor = sqlite3.connect(mpr).cursor()
        cursor.execute("SELECT _ProductVersion FROM _MetaData LIMIT 1")
        record = cursor.fetchone()
        result = record[0]
    return MXVersion(result)


def get_model_version(build_path=BASE_PATH):
    return get_metadata_value("ModelVersion", build_path)


# Extracts REST request handler paths from the static Swagger templates
# included in the model binary
# This is a workaround for the lack of proper REST request handler metadata
# in model/metadata.json
def get_rest_request_handler_paths(build_path=BASE_PATH):
    filename = os.path.join(build_path, "model", "model.mdp")

    # Run the strings command line tool
    # to extract Swagger templates from the model binary
    output = (
        subprocess.check_output(
            ["strings", filename, "|", "grep", "swagger"],
            stderr=subprocess.STDOUT,
        )
        .decode("utf8")
        .strip()
        .split("\n")
    )

    # Extract paths from the Swagger templates
    return _get_paths_from_swagger_templates(output)


def _get_paths_from_swagger_templates(templates):
    # Match templates for basePath and return capture groups
    pattern = r"\"basePath\":\s?\"([a-zA-Z0-9/\.\-_~!$&'()*+,;=:@]+)\""
    result = []
    for template in templates:
        matches = re.search(pattern, template)
        if matches:
            result.append(re.search(pattern, template).group(1))

    return set(result)


def _activate_license():
    prefs_dir = os.path.expanduser("~/../.java/.userPrefs/com/mendix/core")
    util.mkdir_p(prefs_dir)

    prefs_template = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE map SYSTEM "http://java.sun.com/dtd/preferences.dtd">
<map MAP_XML_VERSION="1.0">
  <entry key="id" value="{{LICENSE_ID}}"/>
  <entry key="license_key" value="{{LICENSE_KEY}}"/>
</map>"""

    license_key = os.environ.get(
        "FORCED_LICENSE_KEY", os.environ.get("LICENSE_KEY", None)
    )
    server_id = os.environ.get("FORCED_SERVER_ID", os.environ.get("SERVER_ID", None))
    license_id = os.environ.get("FORCED_LICENSE_ID", os.environ.get("LICENSE_ID", None))
    if server_id:
        logging.warning("SERVER_ID is deprecated, please use LICENSE_ID instead")

    if not license_id:
        license_id = server_id

    if license_key is not None and license_id is not None:
        logging.debug("A license was supplied, activating...")
        prefs_body = prefs_template.replace("{{LICENSE_ID}}", license_id).replace(
            "{{LICENSE_KEY}}", license_key
        )
        with open(os.path.join(prefs_dir, "prefs.xml"), "w") as prefs_file:
            prefs_file.write(prefs_body)


def _get_scheduled_events(metadata):
    scheduled_events = os.getenv("SCHEDULED_EVENTS", None)
    # Scheduled events need to be enabled on every instance >= 9.12
    if get_runtime_version() < MXVersion(9.12) and not util.is_cluster_leader():
        logging.debug(
            "This instance is not a cluster leader, disabling scheduled events..."
        )
        return ("NONE", None)
    elif scheduled_events is None or scheduled_events == "ALL":
        logging.debug("Enabling all scheduled events")
        return ("ALL", None)
    elif scheduled_events == "NONE":
        logging.debug("Disabling all scheduled events")
        return ("NONE", None)
    else:
        parsed_scheduled_events = scheduled_events.split(",")
        metadata_scheduled_events = [
            scheduled_event["Name"] for scheduled_event in metadata["ScheduledEvents"]
        ]
        result = []
        for scheduled_event in parsed_scheduled_events:
            if scheduled_event not in metadata_scheduled_events:
                logging.warning(
                    "Scheduled event defined but not detected in model: [%s]",
                    scheduled_event,
                )
            else:
                result.append(scheduled_event)
        logging.debug("Enabling scheduled events [%s]...", ",".join(result))
        return ("SPECIFIED", result)


def _get_constants(metadata):
    constants = {}

    constants_from_json = {}
    constants_json = os.environ.get("CONSTANTS", json.dumps(constants_from_json))
    try:
        constants_from_json = json.loads(constants_json)
    except Exception:
        logging.warning(
            "Failed to parse model constant values due to invalid JSON, "
            "terminating application...",
            exc_info=True,
        )
        raise

    for constant in metadata["Constants"]:
        constant_name = constant["Name"]
        env_name = f"MX_{constant_name.replace('.', '_')}"
        value = os.environ.get(env_name, constants_from_json.get(constant_name))
        if value is None:
            value = constant["DefaultValue"]
            logging.debug(
                "Constant [%s] not found in environment, using default value...",
                constant_name,
            )
        if constant["Type"] == "Integer":
            value = int(value)
        constants[constant_name] = value
    return constants


def _set_jetty_config(m2ee):
    jetty_config_json = os.environ.get("JETTY_CONFIG")
    if not jetty_config_json:
        return None
    try:
        jetty_config = json.loads(jetty_config_json)
        util.upsert_m2ee_tools_setting(
            m2ee, "jetty", jetty_config, overwrite=True, append=True
        )
        logging.debug(
            "Jetty configured: [%s]",
            json.dumps(util.get_m2ee_tools_setting(m2ee, "jetty")),
        )
    except Exception:
        logging.warning("Failed to configure Jetty", exc_info=True)


def _get_custom_settings(metadata):
    if os.getenv("USE_DATA_SNAPSHOT", "false").lower() == "true":
        custom_settings_key = "Configuration"
        if custom_settings_key in metadata:
            config = {}
            for k, v in metadata[custom_settings_key].items():
                config[k] = v
            return config
    return {}


def _get_license_subscription():
    try:
        vcap_services = util.get_vcap_services_data()
        if "mendix-platform" in vcap_services:
            subscription = vcap_services["mendix-platform"][0]
            logging.debug(
                "Configuring license subscription for [%s]...", subscription["name"]
            )
            credentials = subscription["credentials"]
            return {
                "License.EnvironmentName": credentials["environment_id"],
                "License.LicenseServerURL": credentials["license_server_url"],
                "License.SubscriptionSecret": credentials["secret"],
                "License.UseLicenseServer": True,
            }
    except Exception as exc:
        logging.warning("Failed to configure license subscription: %s", str(exc))
    return {}


def _get_custom_runtime_settings():
    custom_runtime_settings = {}
    custom_runtime_settings_json = os.environ.get(
        "CUSTOM_RUNTIME_SETTINGS", json.dumps(custom_runtime_settings)
    )
    try:
        custom_runtime_settings = json.loads(custom_runtime_settings_json)
    except Exception as exc:
        logging.warning("Failed to parse CUSTOM_RUNTIME_SETTINGS: %s", str(exc))

    for key, value in os.environ.items():
        if key.startswith("MXRUNTIME_"):
            custom_runtime_settings[
                key.replace("MXRUNTIME_", "", 1).replace("_", ".")
            ] = value

    return custom_runtime_settings


def _get_application_root_url(vcap_data):
    try:
        prefix = "http"
        host = vcap_data["application_uris"][0]
        if ".local" in host:
            host = "localhost"
        if host != "localhost":
            prefix += "s"
        return f"{prefix}://{host}"
    except IndexError:
        logging.warning(
            "No application routes are defined. "
            "Your application will not be accessible."
        )
        return ""


def _set_runtime_config(m2ee, metadata, vcap_data):
    scheduled_event_execution, my_scheduled_events = _get_scheduled_events(metadata)

    app_config = {
        "ApplicationRootUrl": _get_application_root_url(vcap_data),
        "MicroflowConstants": _get_constants(metadata),
        "ScheduledEventExecution": scheduled_event_execution,
    }

    if my_scheduled_events is not None:
        app_config["MyScheduledEvents"] = my_scheduled_events

    if util.is_development_mode():
        logging.warning(
            "Runtime is being started in Development mode. "
            'Set \'DEVELOPMENT_MODE\' to "false" (currently "true") '
            "to set it to Production mode."
        )
        app_config["DTAPMode"] = "D"

    if get_runtime_version() >= 7 and not util.is_cluster_leader():
        app_config["com.mendix.core.isClusterSlave"] = "true"
    elif (
        get_runtime_version() >= 6
        and os.getenv("ENABLE_STICKY_SESSIONS", "false").lower() == "true"
    ):
        logging.info("Enabling sticky sessions")
        app_config["com.mendix.core.SessionIdCookieName"] = "JSESSIONID"

    util.mkdir_p(os.path.join(os.getcwd(), "model", "resources"))
    util.upsert_custom_runtime_settings(m2ee, app_config, overwrite=True, append=True)
    util.upsert_custom_runtime_settings(
        m2ee,
        security.get_certificate_authorities(),
        overwrite=True,
        append=True,
    )
    util.upsert_custom_runtime_settings(
        m2ee,
        security.get_client_certificates(get_runtime_version()),
        overwrite=True,
        append=True,
    )
    util.upsert_custom_runtime_settings(
        m2ee, _get_custom_settings(metadata), overwrite=False, append=True
    )
    util.upsert_custom_runtime_settings(
        m2ee, _get_license_subscription(), overwrite=True, append=True
    )
    util.upsert_custom_runtime_settings(
        m2ee, _get_custom_runtime_settings(), overwrite=True, append=True
    )


def _set_application_name(m2ee, name):
    logging.debug("Application name is %s", name)
    util.upsert_m2ee_tools_setting(m2ee, "app_name", name, overwrite=True)


def _configure_debugger(m2ee):
    debugger_password = os.environ.get("DEBUGGER_PASSWORD")

    if debugger_password is None:
        logging.debug(
            "Not configuring debugger: DEBUGGER_PASSWORD environment variable not found"
        )
        return

    response = m2ee.client.enable_debugger({"password": debugger_password})
    response.display_error()
    if not response.has_error():
        logging.info(
            "Remote debugger enabled with value "
            "from DEBUGGER_PASSWORD environment variable"
        )
        logging.debug("The password to use is %s", debugger_password)
        logging.info(
            "You can use the remote debugger option in Mendix Studio Pro to "
            "connect to the /debugger/ path (e.g. https://app.example.com/debugger/)"
        )


def _display_running_model_version(m2ee):
    if get_runtime_version() >= 6.0:
        feedback = m2ee.client.about().get_feedback()
        if "model_version" in feedback:
            logging.info("Model version: [%s]", feedback["model_version"])


def stop(m2ee, timeout=10):
    result = True
    if not _stop(m2ee, timeout):
        logging.debug("Terminating runtime with M2EE...")
        if not m2ee.terminate(timeout):
            logging.warning("Could not terminate runtime")
            result = False
    return result


def _stop(m2ee, timeout=10):
    logging.debug("Stopping runtime with M2EE...")
    if not m2ee.stop(timeout):
        logging.debug("M2EE stop command failed, waiting for process...")
        try:
            os.waitpid(m2ee.runner.get_pid(), os.WNOHANG)
            m2ee.runner.cleanup_pid()
        except OSError as error:
            logging.warning("Waiting for runtime process failed: %s", error)
            return False
    return True


def await_termination(m2ee, interval=1):
    @backoff.on_predicate(backoff.constant, interval=interval, logger=None)
    def _await_termination(m2ee):
        return not m2ee.runner.check_pid()

    if m2ee:
        logging.debug("Waiting until runtime process is terminated...")
        try:
            _await_termination(m2ee)
        except KeyboardInterrupt:
            logging.debug("Waiting for runtime termination interrupted")
        finally:
            logging.debug("Runtime process has been terminated")


def await_database_ready(m2ee, timeout=30):
    logging.info("Waiting for runtime database initialization to complete...")
    if not m2ee.client.ping(timeout):
        raise Exception("Failed to receive successful ping from runtime Admin API")
    logging.info("Runtime database is now available")


def _start_app(m2ee):
    logging.info("The buildpack is starting the runtime...")
    if not m2ee.start_appcontainer():
        raise RuntimeError(
            "Cannot start the Mendix runtime. "
            "Most likely, the runtime is already active or still active"
        )

    @backoff.on_predicate(backoff.expo, max_time=240)
    def _await_runtime_config():
        try:
            result = m2ee.send_runtime_config()
        except Exception:
            result = False
        return result

    is_runtime_config = _await_runtime_config()

    if not is_runtime_config:
        raise RuntimeError("Cannot set runtime configuration")

    logging.debug("Runtime Application Container has been started")

    abort = False
    success = False
    while not (success or abort):
        startresponse = m2ee.client.start({"autocreatedb": True})
        logging.debug("startresponse received")
        result = startresponse.get_result()
        if result == 0:
            success = True
            logging.info("The Mendix runtime has been fully started")
        else:
            startresponse.display_error()
            if result == 2:
                logging.warning("Database does not exist")
                abort = True
            elif result == 3:
                if util.is_cluster_leader():
                    if os.getenv("SHOW_DDL_COMMANDS", "").lower() == "true":
                        for line in m2ee.client.get_ddl_commands(
                            {"verbose": True}
                        ).get_feedback()["ddl_commands"]:
                            logging.info(line)
                    m2eeresponse = m2ee.client.execute_ddl_commands()
                    if m2eeresponse.has_error():
                        m2eeresponse.display_error()
                        abort = True
                else:
                    logging.info(
                        "Waiting 10 seconds before primary instance "
                        "synchronizes database..."
                    )
                    time.sleep(10)
            elif result == 4:
                logging.warning(
                    "Not enough constants, please check your configuration for errors"
                )
                abort = True
            elif result == 5:
                logging.warning(
                    "Unsafe password, please check your configuration for errors"
                )
                abort = True
            elif result == 6:
                logging.warning(
                    "Invalid state, please check your configuration for errors"
                )
                abort = True
            elif result in (7, 8, 9):
                logging.warning("Invalid configuration, please check it for errors")
                abort = True
            else:
                logging.warning(
                    "Unexpected result while starting app: %s."
                    "Please check your configuration for errors",
                    result,
                )
                abort = True
    if abort:
        raise RuntimeError("Application start failed")


def _display_java_version():
    java_version = (
        subprocess.check_output(
            [".local/bin/java", "-version"], stderr=subprocess.STDOUT
        )
        .decode("utf8")
        .strip()
        .split("\n")
    )
    logging.info("Using Java version:")
    for line in java_version:
        logging.info(line)


def _set_loglevels(m2ee, loglevels):
    m2ee.set_log_levels("*", nodes=loglevels, force=True)


def run(m2ee, loglevels):
    # Shutdown handler; called on exit(0) or exit(1)
    def _terminate():
        if m2ee:
            stop(m2ee)

    atexit.register(_terminate)

    _display_java_version()
    util.mkdir_p("model/lib/userlib")
    _start_app(m2ee)
    security.create_admin_user(m2ee, util.is_development_mode())
    _display_running_model_version(m2ee)
    _configure_debugger(m2ee)
    _set_loglevels(m2ee, loglevels)


def _pre_process_m2ee_yaml():
    logging.debug("Preprocessing M2EE defaults...")
    subprocess.check_call(
        [
            "sed",
            "-i",
            f"s|BUILD_PATH|{os.getcwd()}|g; "
            f"s|RUNTIME_PORT|{util.get_runtime_port()}|; "
            f"s|ADMIN_PORT|{util.get_admin_port()}|; "
            f"s|PYTHONPID|{os.getpid()}|",
            ".local/m2ee.yaml",
        ]
    )


def setup(vcap_data):
    _pre_process_m2ee_yaml()
    _activate_license()

    client = m2ee_class(
        yamlfiles=[os.path.abspath(".local/m2ee.yaml")],
        load_default_files=False,
        config={
            "m2ee": {
                # this is named admin_pass, but it's the verification http header
                # to communicate with the internal management port of the runtime
                "admin_pass": security.get_m2ee_password()
            }
        },
    )

    _set_runtime_config(
        client,
        client.config._model_metadata,
        vcap_data,
    )
    _set_application_name(client, vcap_data["application_name"])
    _set_jetty_config(client)

    return client
