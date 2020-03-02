import json
import logging
import os
import sqlite3
import subprocess
import sys
import time

from buildpack import util
from buildpack.runtime_components import (
    backup,
    database,
    logs,
    metrics,
    security,
    storage,
)
from lib.m2ee import logger
from lib.m2ee.version import MXVersion


def check_deprecation(version):
    if version >= MXVersion("5.0.0") and version < MXVersion("6.0.0"):
        logging.error("Mendix Runtime 5.x is no longer supported.")
        logging.error("You can version pin on v3.8.0.")
        return False

    return True


def compile(build_path, cache_path):
    logging.debug("downloading mendix version")

    git_repo_found = os.path.isdir("/usr/local/share/mendix-runtimes.git")

    if git_repo_found and not os.environ.get("FORCED_MXRUNTIME_URL"):
        logging.debug("rootfs with mendix runtime detected, skipping download")
        return

    url = os.environ.get("FORCED_MXRUNTIME_URL")
    if url is not None:
        cache_dir = "/tmp/downloads"
    else:
        cache_dir = cache_path
        url = util.get_blobstore_url(
            "/runtime/mendix-%s.tar.gz" % str(get_version(build_path))
        )
    logging.debug(
        "rootfs without mendix runtimes detected, "
        "downloading and unpacking mendix runtime now"
    )
    util.download_and_unpack(
        url, os.path.join(build_path, "runtimes"), cache_dir=cache_dir
    )


def get_java_version(mx_version):
    if mx_version >= MXVersion("8.0.0"):
        java_version = {
            "version": os.getenv("JAVA_VERSION", "11.0.3"),
            "vendor": "AdoptOpenJDK",
        }
    elif mx_version >= MXVersion("7.23.1"):
        java_version = {
            "version": os.getenv("JAVA_VERSION", "8u202"),
            "vendor": "AdoptOpenJDK",
        }
    elif mx_version >= MXVersion("6.6"):
        java_version = {
            "version": os.getenv("JAVA_VERSION", "8u202"),
            "vendor": "oracle",
        }
    elif mx_version >= MXVersion("6.0"):
        java_version = {
            "version": os.getenv("JAVA_VERSION", "8u51"),
            "vendor": "oracle",
        }
    else:
        java_version = {
            "version": os.getenv("JAVA_VERSION", "7u80"),
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


def activate_license():
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
        logger.warning(
            "SERVER_ID is deprecated, please use LICENSE_ID instead"
        )

    if not license_id:
        license_id = server_id

    if license_key is not None and license_id is not None:
        logger.debug("A license was supplied so going to activate it")
        prefs_body = prefs_template.replace(
            "{{LICENSE_ID}}", license_id
        ).replace("{{LICENSE_KEY}}", license_key)
        with open(os.path.join(prefs_dir, "prefs.xml"), "w") as prefs_file:
            prefs_file.write(prefs_body)


def get_scheduled_events(metadata):
    scheduled_events = os.getenv("SCHEDULED_EVENTS", None)
    if not util.i_am_primary_instance():
        logger.debug(
            "Disabling all scheduled events because I am not the primary "
            "instance"
        )
        return ("NONE", None)
    elif scheduled_events is None or scheduled_events == "ALL":
        logger.debug("Enabling all scheduled events")
        return ("ALL", None)
    elif scheduled_events == "NONE":
        logger.debug("Disabling all scheduled events")
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
                logger.warning(
                    'Scheduled event defined but not detected in model: "%s"',
                    scheduled_event,
                )
            else:
                result.append(scheduled_events)
        logger.debug("Enabling scheduled events %s", ",".join(result))
        return ("SPECIFIED", result)


def get_constants(metadata):
    constants = {}

    constants_from_json = {}
    constants_json = os.environ.get(
        "CONSTANTS", json.dumps(constants_from_json)
    )
    try:
        constants_from_json = json.loads(constants_json)
    except Exception:
        logger.warning(
            "Failed to parse model constant values, due to invalid JSON. "
            "Application terminating.",
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
            logger.debug(
                "Constant not found in environment, taking default "
                "value %s" % constant_name
            )
        if constant["Type"] == "Integer":
            value = int(value)
        constants[constant_name] = value
    return constants


def set_jetty_config(m2ee):
    jetty_config_json = os.environ.get("JETTY_CONFIG")
    if not jetty_config_json:
        return None
    try:
        jetty_config = json.loads(jetty_config_json)
        jetty = m2ee.config._conf["m2ee"]["jetty"]
        jetty.update(jetty_config)
        logger.debug("Jetty configured: %s", json.dumps(jetty))
    except Exception:
        logger.warning("Failed to configure jetty", exc_info=True)


def get_custom_settings(metadata, existing_config):
    if os.getenv("USE_DATA_SNAPSHOT", "false").lower() == "true":
        custom_settings_key = "Configuration"
        if custom_settings_key in metadata:
            config = {}
            for k, v in metadata[custom_settings_key].items():
                if k not in existing_config:
                    config[k] = v
            return config
    return {}


def get_license_subscription():
    try:
        vcap_services = util.get_vcap_services_data()
        if "mendix-platform" in vcap_services:
            subscription = vcap_services["mendix-platform"][0]
            logger.debug(
                "Configuring license subscription for %s"
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
        logger.warning("Failed to configure license subscription: " + str(e))
    return {}


def get_custom_runtime_settings():
    custom_runtime_settings = {}
    custom_runtime_settings_json = os.environ.get(
        "CUSTOM_RUNTIME_SETTINGS", json.dumps(custom_runtime_settings)
    )
    try:
        custom_runtime_settings = json.loads(custom_runtime_settings_json)
    except Exception as e:
        logger.warning("Failed to parse CUSTOM_RUNTIME_SETTINGS: " + str(e))

    for k, v in os.environ.items():
        if k.startswith("MXRUNTIME_"):
            custom_runtime_settings[
                k.replace("MXRUNTIME_", "", 1).replace("_", ".")
            ] = v

    return custom_runtime_settings


def set_runtime_config(metadata, mxruntime_config, vcap_data, m2ee):
    scheduled_event_execution, my_scheduled_events = get_scheduled_events(
        metadata
    )
    app_config = {
        "ApplicationRootUrl": "https://%s" % vcap_data["application_uris"][0],
        "MicroflowConstants": get_constants(metadata),
        "ScheduledEventExecution": scheduled_event_execution,
    }

    if my_scheduled_events is not None:
        app_config["MyScheduledEvents"] = my_scheduled_events

    if util.is_development_mode():
        logger.warning(
            "Runtime is being started in Development Mode. Set "
            'DEVELOPMENT_MODE to "false" (currently "true") to '
            "set it to production."
        )
        app_config["DTAPMode"] = "D"

    if (
        m2ee.config.get_runtime_version() >= 7
        and not util.i_am_primary_instance()
    ):
        app_config["com.mendix.core.isClusterSlave"] = "true"
    elif (
        m2ee.config.get_runtime_version() >= 6
        and os.getenv("ENABLE_STICKY_SESSIONS", "false").lower() == "true"
    ):
        logger.info("Enabling sticky sessions")
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
    mxruntime_config.update(get_custom_settings(metadata, mxruntime_config))
    mxruntime_config.update(get_license_subscription())
    mxruntime_config.update(get_custom_runtime_settings())


def set_application_name(m2ee, name):
    logger.debug("Application name is %s" % name)
    m2ee.config._conf["m2ee"]["app_name"] = name


def configure_debugger(m2ee):
    debugger_password = os.environ.get("DEBUGGER_PASSWORD")

    if debugger_password is None:
        logger.debug(
            "Not configuring debugger, as environment variable "
            "was not found"
        )
        return

    response = m2ee.client.enable_debugger({"password": debugger_password})
    response.display_error()
    if not response.has_error():
        logger.info(
            "The remote debugger is now enabled with the value from "
            "environment variable DEBUGGER_PASSWORD."
        )
        logger.debug("The password to use is %s", debugger_password)
        logger.info(
            "You can use the remote debugger option in the Mendix "
            "Business Modeler to connect to the /debugger/ sub "
            "url on your application (e.g. "
            "https://app.example.com/debugger/). "
        )


def display_running_version(m2ee):
    if m2ee.config.get_runtime_version() >= 6.0:
        feedback = m2ee.client.about().get_feedback()
        if "model_version" in feedback:
            logger.info("Model version: %s", feedback["model_version"])


def complete_start_procedure_safe_to_use_for_restart(m2ee):
    display_java_version()
    util.mkdir_p("model/lib/userlib")
    logs.set_up_logging_file()
    start_app(m2ee)
    security.create_admin_user(m2ee, util.is_development_mode())
    logs.update_config(m2ee)
    display_running_version(m2ee)
    configure_debugger(m2ee)


def start_app(m2ee):
    m2ee.start_appcontainer()
    if not m2ee.send_runtime_config():
        sys.exit(1)

    logger.debug("Appcontainer has been started")

    abort = False
    success = False
    while not (success or abort):
        startresponse = m2ee.client.start({"autocreatedb": True})
        logger.debug("startresponse received")
        result = startresponse.get_result()
        if result == 0:
            success = True
            logger.info("The MxRuntime is fully started now.")
        else:
            startresponse.display_error()
            if result == 2:
                logger.warning("DB does not exists")
                abort = True
            elif result == 3:
                if util.i_am_primary_instance():
                    if os.getenv("SHOW_DDL_COMMANDS", "").lower() == "true":
                        for line in m2ee.client.get_ddl_commands(
                            {"verbose": True}
                        ).get_feedback()["ddl_commands"]:
                            logger.info(line)
                    m2eeresponse = m2ee.client.execute_ddl_commands()
                    if m2eeresponse.has_error():
                        m2eeresponse.display_error()
                        abort = True
                else:
                    logger.info(
                        "waiting 10 seconds before primary instance "
                        "synchronizes database"
                    )
                    time.sleep(10)
            elif result == 4:
                logger.warning("Not enough constants!")
                abort = True
            elif result == 5:
                logger.warning("Unsafe password!")
                abort = True
            elif result == 6:
                logger.warning("Invalid state!")
                abort = True
            elif result == 7 or result == 8 or result == 9:
                logger.warning(
                    "You'll have to fix the configuration and run start "
                    "again... (or ask for help..)"
                )
                abort = True
            else:
                abort = True
    if abort:
        logger.warning("start failed, stopping")
        sys.exit(1)


def display_java_version():
    java_version = (
        subprocess.check_output(
            [".local/bin/java", "-version"], stderr=subprocess.STDOUT
        )
        .decode("utf8")
        .strip()
        .split("\n")
    )
    logger.info("Using Java version:")
    for line in java_version:
        logger.info(line)


def run(m2ee):
    complete_start_procedure_safe_to_use_for_restart(m2ee)


def run_components(m2ee):
    backup.run()
    metrics.run(m2ee)
    logs.run()
