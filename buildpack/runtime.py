import json
import logging
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time

import backoff
from lib.m2ee import M2EE as m2ee_class
from lib.m2ee import logger
from lib.m2ee.version import MXVersion

from buildpack import util
from buildpack.runtime_components import (
    backup,
    database,
    logs,
    metrics,
    security,
    storage,
)

logger.setLevel(util.get_buildpack_loglevel())

# Disable duplicate log lines for M2EE
handlers = logging.getLogger("m2ee").handlers
if len(handlers) > 2:
    logging.getLogger("m2ee").handlers = handlers[:2]
logging.getLogger("m2ee").propagate = False


def check_deprecation(version):
    if version >= MXVersion("5.0.0") and version < MXVersion("6.0.0"):
        return False

    return True


def _get_runtime_url(blobstore, build_path):
    return util.get_blobstore_url(
        "/runtime/mendix-{}.tar.gz".format(str(get_version(build_path))),
        blobstore=blobstore,
    )


def stage(buildpack_dir, build_path, cache_path):

    logging.debug("Creating directory structure for Mendix runtime...")
    for name in ["runtimes", "log", "database", "data", "bin", ".postgresql"]:
        util.mkdir_p(os.path.join(build_path, name))
    for name in ["files", "tmp", "database"]:
        util.mkdir_p(os.path.join(build_path, "data", name))

    logging.debug("Staging required components for Mendix runtime...")
    database.stage(buildpack_dir, build_path)
    logs.stage(buildpack_dir, build_path)

    logging.debug("Staging the Mendix runtime...")
    shutil.copy(
        os.path.join(buildpack_dir, "etc", "m2ee", "m2ee.yaml"),
        os.path.join(build_path, ".local", "m2ee.yaml"),
    )

    git_repo_found = os.path.isdir("/usr/local/share/mendix-runtimes.git")

    if git_repo_found and not os.environ.get("FORCED_MXRUNTIME_URL"):
        logging.debug(
            "Root file system with built-in Mendix runtimes detected, skipping Mendix runtime download"
        )
        return

    forced_url = os.environ.get("FORCED_MXRUNTIME_URL")
    url = None
    if forced_url is not None:
        cache_dir = "/tmp/downloads"
        if not forced_url.endswith(".tar.gz"):
            # Assume that the forced URL points to a blobstore root
            url = _get_runtime_url(forced_url, build_path)
        else:
            url = forced_url
    else:
        cache_dir = cache_path
        url = _get_runtime_url(util.get_blobstore(), build_path)

    logging.debug("Downloading Mendix runtime...")
    util.download_and_unpack(
        url, os.path.join(build_path, "runtimes"), cache_dir=cache_dir
    )


def get_java_version(mx_version):
    if mx_version >= MXVersion("8.0.0"):
        java_version = {
            "version": os.getenv("JAVA_VERSION", "11.0.10"),
            "vendor": "AdoptOpenJDK",
        }
    elif mx_version >= MXVersion("7.23.1"):
        java_version = {
            "version": os.getenv("JAVA_VERSION", "8u282"),
            "vendor": "AdoptOpenJDK",
        }
    else:
        java_version = {
            "version": os.getenv("JAVA_VERSION", "8u261"),
            "vendor": "oracle",
        }

    return java_version


def get_version(build_path):
    file_name = os.path.join(build_path, "model", "metadata.json")
    try:
        with open(file_name) as file_handle:
            data = json.loads(file_handle.read())
            return MXVersion(data["RuntimeVersion"])
    except IOError:
        mpr = util.get_mpr_file_from_dir(build_path)
        if not mpr:
            raise Exception("No model/metadata.json or .mpr found in archive")

        cursor = sqlite3.connect(mpr).cursor()
        cursor.execute("SELECT _ProductVersion FROM _MetaData LIMIT 1")
        record = cursor.fetchone()
        return MXVersion(record[0])


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
    server_id = os.environ.get(
        "FORCED_SERVER_ID", os.environ.get("SERVER_ID", None)
    )
    license_id = os.environ.get(
        "FORCED_LICENSE_ID", os.environ.get("LICENSE_ID", None)
    )
    if server_id:
        logging.warning(
            "SERVER_ID is deprecated, please use LICENSE_ID instead"
        )

    if not license_id:
        license_id = server_id

    if license_key is not None and license_id is not None:
        logging.debug("A license was supplied, activating...")
        prefs_body = prefs_template.replace(
            "{{LICENSE_ID}}", license_id
        ).replace("{{LICENSE_KEY}}", license_key)
        with open(os.path.join(prefs_dir, "prefs.xml"), "w") as prefs_file:
            prefs_file.write(prefs_body)


def _get_scheduled_events(metadata):
    scheduled_events = os.getenv("SCHEDULED_EVENTS", None)
    if not util.is_cluster_leader():
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
            scheduled_event["Name"]
            for scheduled_event in metadata["ScheduledEvents"]
        ]
        result = []
        for scheduled_event in parsed_scheduled_events:
            if scheduled_event not in metadata_scheduled_events:
                logging.warning(
                    "Scheduled event defined but not detected in model: [%s]",
                    scheduled_event,
                )
            else:
                result.append(scheduled_events)
        logging.debug("Enabling scheduled events [%s]...", ",".join(result))
        return ("SPECIFIED", result)


def _get_constants(metadata):
    constants = {}

    constants_from_json = {}
    constants_json = os.environ.get(
        "CONSTANTS", json.dumps(constants_from_json)
    )
    try:
        constants_from_json = json.loads(constants_json)
    except Exception:
        logging.warning(
            "Failed to parse model constant values due to invalid JSON, terminating application...",
            exc_info=True,
        )
        raise

    for constant in metadata["Constants"]:
        constant_name = constant["Name"]
        env_name = "MX_%s" % constant_name.replace(".", "_")
        value = os.environ.get(
            env_name, constants_from_json.get(constant_name)
        )
        if value is None:
            value = constant["DefaultValue"]
            logging.debug(
                "Constant [%s] not found in environment, using default value..."
                % constant_name
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
        jetty = m2ee.config._conf["m2ee"]["jetty"]
        jetty.update(jetty_config)
        logging.debug("Jetty configured: [%s]", json.dumps(jetty))
    except Exception:
        logging.warning("Failed to configure Jetty", exc_info=True)


def _get_custom_settings(metadata, existing_config):
    if os.getenv("USE_DATA_SNAPSHOT", "false").lower() == "true":
        custom_settings_key = "Configuration"
        if custom_settings_key in metadata:
            config = {}
            for k, v in metadata[custom_settings_key].items():
                if k not in existing_config:
                    config[k] = v
            return config
    return {}


def _get_license_subscription():
    try:
        vcap_services = util.get_vcap_services_data()
        if "mendix-platform" in vcap_services:
            subscription = vcap_services["mendix-platform"][0]
            logging.debug(
                "Configuring license subscription for [%s]..."
                % subscription["name"]
            )
            credentials = subscription["credentials"]
            return {
                "License.EnvironmentName": credentials["environment_id"],
                "License.LicenseServerURL": credentials["license_server_url"],
                "License.SubscriptionSecret": credentials["secret"],
                "License.UseLicenseServer": True,
            }
    except Exception as e:
        logging.warning("Failed to configure license subscription: " + str(e))
    return {}


def _get_custom_runtime_settings():
    custom_runtime_settings = {}
    custom_runtime_settings_json = os.environ.get(
        "CUSTOM_RUNTIME_SETTINGS", json.dumps(custom_runtime_settings)
    )
    try:
        custom_runtime_settings = json.loads(custom_runtime_settings_json)
    except Exception as e:
        logging.warning("Failed to parse CUSTOM_RUNTIME_SETTINGS: " + str(e))

    for k, v in os.environ.items():
        if k.startswith("MXRUNTIME_"):
            custom_runtime_settings[
                k.replace("MXRUNTIME_", "", 1).replace("_", ".")
            ] = v

    return custom_runtime_settings


def _get_application_root_url(vcap_data):
    try:
        prefix = "http"
        host = vcap_data["application_uris"][0]
        if ".local" in host:
            host = "localhost"
        if host != "localhost":
            prefix += "s"
        return "{}://{}".format(prefix, host)
    except IndexError:
        logging.warning(
            "No application routes are defined. Your application will not be accessible."
        )
        return ""


def _set_runtime_config(metadata, mxruntime_config, vcap_data, m2ee):
    scheduled_event_execution, my_scheduled_events = _get_scheduled_events(
        metadata
    )

    app_config = {
        "ApplicationRootUrl": _get_application_root_url(vcap_data),
        "MicroflowConstants": _get_constants(metadata),
        "ScheduledEventExecution": scheduled_event_execution,
    }

    if my_scheduled_events is not None:
        app_config["MyScheduledEvents"] = my_scheduled_events

    if util.is_development_mode():
        logging.warning(
            'Runtime is being started in Development mode. Set \'DEVELOPMENT_MODE to "false" (currently "true") to set it to Production mode.'
        )
        app_config["DTAPMode"] = "D"

    if m2ee.config.get_runtime_version() >= 7 and not util.is_cluster_leader():
        app_config["com.mendix.core.isClusterSlave"] = "true"
    elif (
        m2ee.config.get_runtime_version() >= 6
        and os.getenv("ENABLE_STICKY_SESSIONS", "false").lower() == "true"
    ):
        logging.info("Enabling sticky sessions")
        app_config["com.mendix.core.SessionIdCookieName"] = "JSESSIONID"

    util.mkdir_p(os.path.join(os.getcwd(), "model", "resources"))
    mxruntime_config.update(app_config)

    # db configuration might be None, database should then be set up with
    # MXRUNTIME_Database... custom runtime settings.
    runtime_db_config = database.get_config()
    if runtime_db_config:
        mxruntime_config.update(runtime_db_config)

    mxruntime_config.update(storage.get_config(m2ee))
    mxruntime_config.update(security.get_certificate_authorities())
    mxruntime_config.update(
        security.get_client_certificates(m2ee.config.get_runtime_version())
    )
    mxruntime_config.update(_get_custom_settings(metadata, mxruntime_config))
    mxruntime_config.update(_get_license_subscription())
    mxruntime_config.update(_get_custom_runtime_settings())


def _set_application_name(m2ee, name):
    logging.debug("Application name is %s" % name)
    m2ee.config._conf["m2ee"]["app_name"] = name


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
            "Remote debugger enabled with value from DEBUGGER_PASSWORD environment variable"
        )
        logging.debug("The password to use is %s", debugger_password)
        logging.info(
            "You can use the remote debugger option in Mendix Studio Pro to connect to the /debugger/ path (e.g. https://app.example.com/debugger/)"
        )


def _display_running_version(m2ee):
    if m2ee.config.get_runtime_version() >= 6.0:
        feedback = m2ee.client.about().get_feedback()
        if "model_version" in feedback:
            logging.info("Model version: [%s]", feedback["model_version"])


def stop(m2ee, timeout=10):
    result = True
    if not _stop(m2ee, timeout):
        logging.debug("Terminating runtime with M2EE...")
        if not m2ee.terminate(timeout):
            logging.debug(
                "M2EE terminate command failed, killing runtime with M2EE..."
            )
            if not m2ee.kill(timeout):
                logging.warning("M2EE could not kill runtime")
                result = False
    metrics.emit(jvm={"crash": 1.0})
    return result


def _stop(m2ee, timeout=10):
    logging.debug("Stopping runtime with M2EE...")
    if not m2ee.stop(timeout):
        logging.debug("M2EE stop command failed, waiting for process...")
        try:
            os.waitpid(m2ee.runner.get_pid(), os.WNOHANG)
            m2ee.runner.cleanup_pid()
        except OSError as error:
            logging.warning(
                "Waiting for runtime process failed: {}".format(error)
            )
            return False
    return True


def await_termination(m2ee):
    @backoff.on_predicate(backoff.constant, interval=10, logger=None)
    def _await_termination(m2ee):
        return not m2ee.runner.check_pid()

    logging.debug("Waiting until runtime process terminates...")
    _await_termination(m2ee)
    logging.info("Runtime process terminated")


def await_database_ready(m2ee, timeout=30):
    logging.info("Waiting for runtime database initialization to complete...")
    if not m2ee.client.ping(timeout):
        raise Exception(
            "Failed to receive successful ping from runtime Admin API"
        )
    logging.info("Runtime database is now available")


def _start_app(m2ee):
    logging.info("The buildpack is starting the runtime...")
    if not m2ee.start_appcontainer():
        logging.error(
            "Cannot start the Mendix runtime. Most likely, the runtime is already active or still active"
        )
        sys.exit(1)

    @backoff.on_predicate(backoff.expo, max_time=240)
    def _await_runtime_config():
        try:
            result = m2ee.send_runtime_config()
        except Exception:
            result = False
        return result

    is_runtime_config = _await_runtime_config()

    if not is_runtime_config:
        logging.error("Cannot set runtime configuration")
        sys.exit(1)

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
                        "Waiting 10 seconds before primary instance synchronizes database..."
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
            elif result == 7 or result == 8 or result == 9:
                logging.warning(
                    "Invalid configuration, please check it for errors"
                )
                abort = True
            else:
                abort = True
    if abort:
        logging.warning(
            "Application start failed, stopping the Mendix Runtime..."
        )
        sys.exit(1)


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


def run(m2ee):
    # Handler for user signals
    def sigusr_handler(_signo, _stack_frame):
        logging.debug("Handling SIGUSR...")
        if _signo == signal.SIGUSR1:
            metrics.emit(jvm={"errors": 1.0})
        elif _signo == signal.SIGUSR2:
            metrics.emit(jvm={"ooms": 1.0})
        else:
            pass
        sys.exit(1)

    # Handler for child process signals
    def sigchild_handler(_signo, _stack_frame):
        logging.debug("Handling SIGCHILD...")
        os.waitpid(-1, os.WNOHANG)

    signal.signal(signal.SIGCHLD, sigchild_handler)
    signal.signal(signal.SIGUSR1, sigusr_handler)
    signal.signal(signal.SIGUSR2, sigusr_handler)

    _display_java_version()
    util.mkdir_p("model/lib/userlib")
    logs.set_up_logging_file()
    _start_app(m2ee)
    security.create_admin_user(m2ee, util.is_development_mode())
    logs.update_config(m2ee)
    _display_running_version(m2ee)
    _configure_debugger(m2ee)

    backup.run()
    metrics.run(m2ee)
    logs.run()


def _pre_process_m2ee_yaml():
    logging.debug("Preprocessing M2EE defaults...")
    subprocess.check_call(
        [
            "sed",
            "-i",
            "s|BUILD_PATH|%s|g; s|RUNTIME_PORT|%d|; s|ADMIN_PORT|%d|; s|PYTHONPID|%d|"
            % (
                os.getcwd(),
                util.get_runtime_port(),
                util.get_admin_port(),
                os.getpid(),
            ),
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

    version = client.config.get_runtime_version()

    mendix_runtimes_path = "/usr/local/share/mendix-runtimes.git"
    mendix_runtime_version_path = os.path.join(
        os.getcwd(), "runtimes", str(version)
    )
    if os.path.isdir(mendix_runtimes_path) and not os.path.isdir(
        mendix_runtime_version_path
    ):
        util.mkdir_p(mendix_runtime_version_path)
        env = dict(os.environ)
        env["GIT_WORK_TREE"] = mendix_runtime_version_path

        # checkout the runtime version
        process = subprocess.Popen(
            ["git", "checkout", str(version), "-f"],
            cwd=mendix_runtimes_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        process.communicate()
        if process.returncode != 0:
            logging.info(
                "Mendix [%s] is not available in the root file system", version
            )
            logging.info(
                "Fallback (1): trying to fetch Mendix [%s] using git...",
                version,
            )
            process = subprocess.Popen(
                [
                    "git",
                    "fetch",
                    "origin",
                    "refs/tags/{0}:refs/tags/{0}".format(str(version)),
                    "&&",
                    "git",
                    "checkout",
                    str(version),
                    "-f",
                ],
                cwd=mendix_runtimes_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            process.communicate()
            if process.returncode != 0:
                logging.info(
                    "Unable to fetch Mendix [{}] using git".format(version)
                )
                url = util.get_blobstore_url(
                    "/runtime/mendix-%s.tar.gz" % str(version)
                )
                logging.info(
                    "Fallback (2): downloading Mendix [{}] from [{}]...".format(
                        version, url
                    )
                )
                util.download_and_unpack(
                    url, os.path.join(os.getcwd(), "runtimes")
                )

        client.reload_config()
    _set_runtime_config(
        client.config._model_metadata,
        client.config._conf["mxruntime"],
        vcap_data,
        client,
    )

    _set_application_name(client, vcap_data["application_name"])

    _set_jetty_config(client)
    return client
