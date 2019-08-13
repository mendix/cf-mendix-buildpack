#!/usr/bin/env python3
import atexit
import base64
import datetime
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, "lib")
import requests  # noqa: E402

import buildpackutil  # noqa: E402
import database_config  # noqa: E402
import datadog  # noqa: E402
import instadeploy  # noqa: E402
import telegraf  # noqa: E402
from headers import parse_headers  # noqa: E402

from m2ee import M2EE, logger  # noqa: E402
from nginx import get_path_config, gen_htpasswd  # noqa: E402
from buildpackutil import i_am_primary_instance  # noqa: E402

BUILDPACK_VERSION = "3.6.1"


logger.setLevel(buildpackutil.get_buildpack_loglevel())


def get_current_buildpack_commit():
    try:
        with open(".buildpack_commit", "r") as commit_file:
            short_commit = commit_file.readline().strip()
            return short_commit
    except Exception:
        logger.debug("Failed to read file", exc_info=True)
        return "unknown_commit"


logger.info(
    "Started Mendix Cloud Foundry Buildpack v%s [commit:%s]",
    BUILDPACK_VERSION,
    get_current_buildpack_commit(),
)
logging.getLogger("m2ee").propagate = False

app_is_restarting = False
default_m2ee_password = str(uuid.uuid4()).replace("-", "@") + "A1"
nginx_process = None
m2ee = None
MAINTENANCE_MESSAGE = (
    "App is in maintenance mode. To turn off unset DEBUG_CONTAINER variable"
)


class Maintenance(BaseHTTPRequestHandler):
    def _handle_all(self):
        logger.warning(MAINTENANCE_MESSAGE)
        self.send_response(503)
        self.send_header("X-Mendix-Cloud-Mode", "maintenance")
        self.end_headers()
        self.wfile.write(MAINTENANCE_MESSAGE.encode("utf-8"))

    def do_GET(self):
        self._handle_all()

    def do_POST(self):
        self._handle_all()

    def do_PUT(self):
        self._handle_all()

    def do_HEAD(self):
        self._handle_all()


if os.environ.get("DEBUG_CONTAINER", "false").lower() == "true":
    logger.warning(MAINTENANCE_MESSAGE)
    port = int(os.environ.get("PORT", 8080))
    httpd = HTTPServer(("", port), Maintenance)
    httpd.serve_forever()


def emit(**stats):
    stats["version"] = "1.0"
    stats["timestamp"] = datetime.datetime.now().isoformat()
    logger.info("MENDIX-METRICS: " + json.dumps(stats))


def get_nginx_port():
    return int(os.environ["PORT"])


def get_runtime_port():
    return get_nginx_port() + 1


def get_admin_port():
    return get_nginx_port() + 2


def get_deploy_port():
    return get_nginx_port() + 3


def pre_process_m2ee_yaml():
    subprocess.check_call(
        [
            "sed",
            "-i",
            "s|BUILD_PATH|%s|g; s|RUNTIME_PORT|%d|; s|ADMIN_PORT|%d|; s|PYTHONPID|%d|"
            % (os.getcwd(), get_runtime_port(), get_admin_port(), os.getpid()),
            ".local/m2ee.yaml",
        ]
    )


def use_instadeploy(mx_version):
    return mx_version >= 6.7


def get_admin_password():
    return os.getenv("ADMIN_PASSWORD")


def get_m2ee_password():
    m2ee_password = os.getenv("M2EE_PASSWORD", get_admin_password())
    if not m2ee_password:
        logger.debug(
            "No ADMIN_PASSWORD or M2EE_PASSWORD configured, using a random password for the m2ee admin api"
        )
        m2ee_password = default_m2ee_password
    return m2ee_password


def set_up_nginx_files(m2ee):
    lines = ""

    if use_instadeploy(m2ee.config.get_runtime_version()):
        mxbuild_upstream = "proxy_pass http://mendix_mxbuild"
    else:
        mxbuild_upstream = "return 501"
    with open("nginx/conf/nginx.conf") as fh:
        lines = "".join(fh.readlines())
    http_headers = parse_headers()
    lines = (
        lines.replace("CONFIG", get_path_config())
        .replace("NGINX_PORT", str(get_nginx_port()))
        .replace("RUNTIME_PORT", str(get_runtime_port()))
        .replace("ADMIN_PORT", str(get_admin_port()))
        .replace("DEPLOY_PORT", str(get_deploy_port()))
        .replace("ROOT", os.getcwd())
        .replace("HTTP_HEADERS", http_headers)
        .replace("MXBUILD_UPSTREAM", mxbuild_upstream)
    )
    for line in lines.split("\n"):
        logger.debug(line)
    with open("nginx/conf/nginx.conf", "w") as fh:
        fh.write(lines)

    gen_htpasswd({"MxAdmin": get_m2ee_password()})
    gen_htpasswd(
        {"deploy": os.getenv("DEPLOY_PASSWORD")}, file_name_suffix="-mxbuild"
    )


def start_nginx():
    global nginx_process
    nginx_process = subprocess.Popen(
        ["nginx/sbin/nginx", "-p", "nginx", "-c", "conf/nginx.conf"]
    )


def activate_license():
    prefs_dir = os.path.expanduser("~/../.java/.userPrefs/com/mendix/core")
    buildpackutil.mkdir_p(prefs_dir)

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
    if not i_am_primary_instance():
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
                    'Scheduled event defined but not detected in model: "%s"'
                    % scheduled_event
                )
            else:
                result.append(scheduled_events)
        logger.debug("Enabling scheduled events %s" % ",".join(result))
        return ("SPECIFIED", result)


def get_constants(metadata):
    constants = {}

    constants_from_json = {}
    constants_json = os.environ.get(
        "CONSTANTS", json.dumps(constants_from_json)
    )
    try:
        constants_from_json = json.loads(constants_json)
    except Exception as e:
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


def set_jvm_locale(m2ee_section, java_version):
    javaopts = m2ee_section["javaopts"]

    # override locale providers for java8
    if java_version.startswith("8"):
        javaopts.append("-Djava.locale.providers=JRE,SPI,CLDR")


def set_user_provided_java_options(m2ee_section):
    javaopts = m2ee_section["javaopts"]
    options = os.environ.get("JAVA_OPTS", None)
    if options:
        try:
            options = json.loads(options)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse JAVA_OPTS, due to invalid JSON.",
                exc_info=True,
            )
            raise
        javaopts.extend(options)


def set_jvm_memory(m2ee_section, vcap, java_version):
    max_memory = os.environ.get("MEMORY_LIMIT")

    if max_memory:
        match = re.search("([0-9]+)M", max_memory.upper())
        limit = int(match.group(1))
    else:
        limit = int(vcap["limits"]["mem"])

    if limit >= 8192:
        heap_size = limit - 2048
    elif limit >= 4096:
        heap_size = limit - 1536
    elif limit >= 2048:
        heap_size = limit - 1024
    else:
        heap_size = int(limit / 2)

    heap_size = str(heap_size) + "M"

    env_heap_size = os.environ.get("HEAP_SIZE")
    if env_heap_size:
        if int(env_heap_size[:-1]) < limit:
            heap_size = env_heap_size
        else:
            logger.warning(
                "specified heap size {} is larger than max memory of the "
                "container ({}), falling back to a heap size of {}".format(
                    env_heap_size, str(limit) + "M", heap_size
                )
            )
    javaopts = m2ee_section["javaopts"]

    javaopts.append("-Xmx%s" % heap_size)
    javaopts.append("-Xms%s" % heap_size)

    if java_version.startswith("7"):
        javaopts.append("-XX:MaxPermSize=256M")
    else:
        javaopts.append("-XX:MaxMetaspaceSize=256M")

    logger.debug("Java heap size set to %s" % heap_size)

    if os.getenv("MALLOC_ARENA_MAX"):
        logger.info("Using provided environment setting for MALLOC_ARENA_MAX")
    else:
        m2ee_section["custom_environment"]["MALLOC_ARENA_MAX"] = str(
            max(1, limit / 1024) * 2
        )


def set_jetty_config(m2ee):
    jetty_config_json = os.environ.get("JETTY_CONFIG")
    if not jetty_config_json:
        return None
    try:
        jetty_config = json.loads(jetty_config_json)
        jetty = m2ee.config._conf["m2ee"]["jetty"]
        jetty.update(jetty_config)
        logger.debug("Jetty configured: %s", json.dumps(jetty))
    except Exception as e:
        logger.warning("Failed to configure jetty", exc_info=True)


def _get_s3_specific_config(vcap_services, m2ee):
    access_key = secret = bucket = encryption_keys = key_suffix = None
    endpoint = None
    v2_auth = ""
    amazon_s3 = None

    for key in vcap_services:
        if key.startswith("amazon-s3") or key == "objectstore":
            amazon_s3 = key

    if amazon_s3:
        _conf = vcap_services[amazon_s3][0]["credentials"]
        access_key = _conf["access_key_id"]
        secret = _conf["secret_access_key"]
        bucket = _conf["bucket"]  # see below at hacky for actual conf
        if "encryption_keys" in _conf:
            encryption_keys = _conf["encryption_keys"]
        if "key_suffix" in _conf:
            key_suffix = _conf["key_suffix"]
        if "host" in _conf:
            endpoint = _conf["host"]
        if "endpoint" in _conf:
            endpoint = _conf["endpoint"]

        # hacky way to switch from suffix to prefix configuration
        if "key_prefix" in _conf and "endpoint" in _conf:
            bucket = _conf["key_prefix"].replace("/", "")
            endpoint = _conf["endpoint"] + "/" + _conf["bucket"]
            key_suffix = None

    elif "p-riakcs" in vcap_services:
        _conf = vcap_services["p-riakcs"][0]["credentials"]
        access_key = _conf["access_key_id"]
        secret = _conf["secret_access_key"]
        pattern = r"https://(([^:]+):([^@]+)@)?([^/]+)/(.*)"
        match = re.search(pattern, _conf["uri"])
        endpoint = "https://" + match.group(4)
        bucket = match.group(5)
        v2_auth = "true"

    access_key = os.getenv("S3_ACCESS_KEY_ID", access_key)
    secret = os.getenv("S3_SECRET_ACCESS_KEY", secret)
    bucket = os.getenv("S3_BUCKET_NAME", bucket)
    if "S3_ENCRYPTION_KEYS" in os.environ:
        encryption_keys = json.loads(os.getenv("S3_ENCRYPTION_KEYS"))

    dont_perform_deletes = (
        os.getenv("S3_PERFORM_DELETES", "true").lower() == "false"
    )
    key_suffix = os.getenv("S3_KEY_SUFFIX", key_suffix)
    endpoint = os.getenv("S3_ENDPOINT", endpoint)
    v2_auth = os.getenv("S3_USE_V2_AUTH", v2_auth).lower() == "true"
    sse = os.getenv("S3_USE_SSE", "").lower() == "true"

    if not (access_key and secret and bucket):
        return None

    logger.info("S3 config detected, activating external file store")
    config = {
        "com.mendix.core.StorageService": "com.mendix.storage.s3",
        "com.mendix.storage.s3.AccessKeyId": access_key,
        "com.mendix.storage.s3.SecretAccessKey": secret,
        "com.mendix.storage.s3.BucketName": bucket,
    }

    if dont_perform_deletes:
        logger.debug("disabling perform deletes for runtime")
        if m2ee.config.get_runtime_version() < 7.19:
            # Deprecated in 7.19
            config["com.mendix.storage.s3.PerformDeleteFromStorage"] = False
        else:
            config["com.mendix.storage.PerformDeleteFromStorage"] = False
    if key_suffix:
        config["com.mendix.storage.s3.ResourceNameSuffix"] = key_suffix
    if v2_auth:
        config["com.mendix.storage.s3.UseV2Auth"] = v2_auth
    if endpoint:
        config["com.mendix.storage.s3.EndPoint"] = endpoint
    if m2ee.config.get_runtime_version() >= 5.17 and encryption_keys:
        config["com.mendix.storage.s3.EncryptionKeys"] = encryption_keys
    if m2ee.config.get_runtime_version() >= 6 and sse:
        config["com.mendix.storage.s3.UseSSE"] = sse
    return config


def _get_swift_specific_config(vcap_services, m2ee):
    if "Object-Storage" not in vcap_services:
        return None

    if m2ee.config.get_runtime_version() < 6.7:
        logger.warning("Can not configure Object Storage with Mendix < 6.7")
        return None

    creds = vcap_services["Object-Storage"][0]["credentials"]

    container_name = os.getenv("SWIFT_CONTAINER_NAME", "mendix")

    return {
        "com.mendix.core.StorageService": "com.mendix.storage.swift",
        "com.mendix.storage.swift.Container": container_name,
        "com.mendix.storage.swift.Container.AutoCreate": True,
        "com.mendix.storage.swift.credentials.DomainId": creds["domainId"],
        "com.mendix.storage.swift.credentials.Authurl": creds["auth_url"],
        "com.mendix.storage.swift.credentials.Username": creds["username"],
        "com.mendix.storage.swift.credentials.Password": creds["password"],
        "com.mendix.storage.swift.credentials.Region": creds["region"],
    }


def _get_azure_storage_specific_config(vcap_services, m2ee):
    if "azure-storage" not in vcap_services:
        return None

    if m2ee.config.get_runtime_version() < 6.7:
        logger.warning("Can not configure Azure Storage with Mendix < 6.7")
        return None

    creds = vcap_services["azure-storage"][0]["credentials"]

    container_name = os.getenv("AZURE_CONTAINER_NAME", "mendix")

    return {
        "com.mendix.core.StorageService": "com.mendix.storage.azure",
        "com.mendix.storage.azure.Container": container_name,
        "com.mendix.storage.azure.AccountName": creds["storage_account_name"],
        "com.mendix.storage.azure.AccountKey": creds["primary_access_key"],
    }


def get_filestore_config(m2ee):
    vcap_services = buildpackutil.get_vcap_services_data()

    config = _get_s3_specific_config(vcap_services, m2ee)

    if config is None:
        config = _get_swift_specific_config(vcap_services, m2ee)

    if config is None:
        config = _get_azure_storage_specific_config(vcap_services, m2ee)

    if config is None:
        logger.warning(
            "External file store not configured, uploaded files in the app "
            "will not persist across restarts. See https://github.com/mendix/"
            "cf-mendix-buildpack for file store configuration details."
        )
        return {}
    else:
        return config


def get_certificate_authorities():
    config = {}
    cas = os.getenv("CERTIFICATE_AUTHORITIES", None)
    if cas:
        ca_list = cas.split("-----BEGIN CERTIFICATE-----")
        n = 0
        files = []
        for ca in ca_list:
            if "-----END CERTIFICATE-----" in ca:
                ca = "-----BEGIN CERTIFICATE-----" + ca
                location = os.path.abspath(
                    ".local/certificate_authorities.%d.crt" % n
                )
                with open(location, "w") as output_file:
                    output_file.write(ca)
                files.append(location)
                n += 1
        config["CACertificates"] = ",".join(files)
    return config


def get_client_certificates():
    config = {}
    client_certificates_json = os.getenv("CLIENT_CERTIFICATES", "[]")
    """
    [
        {
        'pfx': 'base64...', # required
        'password': '',
        'pin_to': ['Module.WS1', 'Module2.WS2'] # optional
        },
        {...}
    ]
    """
    client_certificates = json.loads(client_certificates_json)
    num = 0
    files = []
    passwords = []
    pins = {}
    for client_certificate in client_certificates:
        pfx = base64.b64decode(client_certificate["pfx"])
        location = os.path.abspath(".local/client_certificate.%d.crt" % num)
        with open(location, "wb") as f:
            f.write(pfx)
        passwords.append(client_certificate["password"])
        files.append(location)
        if "pin_to" in client_certificate:
            for ws in client_certificate["pin_to"]:
                pins[ws] = location
        num += 1
    if len(files) > 0:
        config["ClientCertificates"] = ",".join(files)
        config["ClientCertificatePasswords"] = ",".join(passwords)
        config["WebServiceClientCertificates"] = pins
    return config


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
        vcap_services = buildpackutil.get_vcap_services_data()
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


def is_development_mode():
    return os.getenv("DEVELOPMENT_MODE", "").lower() == "true"


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

    if is_development_mode():
        logger.warning(
            "Runtime is being started in Development Mode. Set "
            'DEVELOPMENT_MODE to "false" (currently "true") to '
            "set it to production."
        )
        app_config["DTAPMode"] = "D"

    if m2ee.config.get_runtime_version() >= 7 and not i_am_primary_instance():
        app_config["com.mendix.core.isClusterSlave"] = "true"
    elif (
        m2ee.config.get_runtime_version() >= 5.15
        and os.getenv("ENABLE_STICKY_SESSIONS", "false").lower() == "true"
    ):
        logger.info("Enabling sticky sessions")
        app_config["com.mendix.core.SessionIdCookieName"] = "JSESSIONID"

    buildpackutil.mkdir_p(os.path.join(os.getcwd(), "model", "resources"))
    mxruntime_config.update(app_config)

    # db configuration might be None, database should then be set up with
    # MXRUNTIME_Database... custom runtime settings.
    runtime_db_config = database_config.get_database_config(
        development_mode=is_development_mode()
    )
    if runtime_db_config:
        mxruntime_config.update(runtime_db_config)

    mxruntime_config.update(get_filestore_config(m2ee))
    mxruntime_config.update(get_certificate_authorities())
    mxruntime_config.update(get_client_certificates())
    mxruntime_config.update(get_custom_settings(metadata, mxruntime_config))
    mxruntime_config.update(get_license_subscription())
    mxruntime_config.update(get_custom_runtime_settings())


def set_application_name(m2ee, name):
    logger.debug("Application name is %s" % name)
    m2ee.config._conf["m2ee"]["app_name"] = name


def activate_appdynamics(m2ee, app_name):
    if not buildpackutil.appdynamics_used():
        return
    logger.info("Adding app dynamics")
    m2ee.config._conf["m2ee"]["javaopts"].append(
        "-javaagent:{path}".format(
            path=os.path.abspath(".local/ver4.3.5.7/javaagent.jar")
        )
    )
    m2ee.config._conf["m2ee"]["javaopts"].append(
        "-Dappagent.install.dir={path}".format(
            path=os.path.abspath(".local/ver4.3.5.7")
        )
    )
    APPDYNAMICS_AGENT_NODE_NAME = "APPDYNAMICS_AGENT_NODE_NAME"
    if os.getenv(APPDYNAMICS_AGENT_NODE_NAME):
        m2ee.config._conf["m2ee"]["custom_environment"][
            APPDYNAMICS_AGENT_NODE_NAME
        ] = (
            "%s-%s"
            % (
                os.getenv(APPDYNAMICS_AGENT_NODE_NAME),
                os.getenv("CF_INSTANCE_INDEX", "0"),
            )
        )


def activate_new_relic(m2ee, app_name):
    if buildpackutil.get_new_relic_license_key() is None:
        logger.debug(
            "Skipping New Relic setup, no license key found in environment"
        )
        return
    logger.info("Adding new relic")
    m2ee_section = m2ee.config._conf["m2ee"]
    if "custom_environment" not in m2ee_section:
        m2ee_section["custom_environment"] = {}
    m2ee_section["custom_environment"][
        "NEW_RELIC_LICENSE_KEY"
    ] = buildpackutil.get_new_relic_license_key()
    m2ee_section["custom_environment"]["NEW_RELIC_APP_NAME"] = app_name
    m2ee_section["custom_environment"]["NEW_RELIC_LOG"] = os.path.abspath(
        "newrelic/agent.log"
    )

    m2ee.config._conf["m2ee"]["javaopts"].append(
        "-javaagent:{path}".format(
            path=os.path.abspath("newrelic/newrelic.jar")
        )
    )


def set_up_m2ee_client(vcap_data):
    m2ee = M2EE(
        yamlfiles=[".local/m2ee.yaml"],
        load_default_files=False,
        config={
            "m2ee": {
                # this is named admin_pass, but it's the verification http header
                # to communicate with the internal management port of the runtime
                "admin_pass": get_m2ee_password()
            }
        },
    )
    version = m2ee.config.get_runtime_version()

    mendix_runtimes_path = "/usr/local/share/mendix-runtimes.git"
    mendix_runtime_version_path = os.path.join(
        os.getcwd(), "runtimes", str(version)
    )
    if os.path.isdir(mendix_runtimes_path) and not os.path.isdir(
        mendix_runtime_version_path
    ):
        buildpackutil.mkdir_p(mendix_runtime_version_path)
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
            logger.info(
                "Mendix {} is not available in the rootfs".format(version)
            )
            logger.info(
                "Fallback (1): trying to fetch Mendix {} using git".format(
                    version
                )
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
                logger.info(
                    "Unable to fetch Mendix {} using git".format(version)
                )
                url = buildpackutil.get_blobstore_url(
                    "/runtime/mendix-%s.tar.gz" % str(version)
                )
                logger.info(
                    "Fallback (2): downloading Mendix {} from {}".format(
                        version, url
                    )
                )
                buildpackutil.download_and_unpack(
                    url, os.path.join(os.getcwd(), "runtimes")
                )

        m2ee.reload_config()
    set_runtime_config(
        m2ee.config._model_metadata,
        m2ee.config._conf["mxruntime"],
        vcap_data,
        m2ee,
    )
    java_version = buildpackutil.get_java_version(
        m2ee.config.get_runtime_version()
    )["version"]
    set_jvm_memory(m2ee.config._conf["m2ee"], vcap_data, java_version)
    set_jvm_locale(m2ee.config._conf["m2ee"], java_version)
    set_user_provided_java_options(m2ee.config._conf["m2ee"])
    set_jetty_config(m2ee)
    activate_new_relic(m2ee, vcap_data["application_name"])
    activate_appdynamics(m2ee, vcap_data["application_name"])
    set_application_name(m2ee, vcap_data["application_name"])
    telegraf.update_config(m2ee, vcap_data["application_name"])
    datadog.update_config(m2ee, vcap_data["application_name"])
    return m2ee


class LogFilterThread(threading.Thread):
    def __init__(self, log_ratelimit):
        super().__init__()
        self.log_ratelimit = log_ratelimit

    def run(self):
        try:
            while True:
                proc = subprocess.Popen(
                    [
                        "./bin/mendix-logfilter",
                        "-r",
                        self.log_ratelimit,
                        "-f",
                        "log/out.log",
                    ]
                )
                proc.wait()
                logger.warning(
                    "MENDIX LOGGING: Mendix logfilter crashed with return code "
                    "%s. This is nothing to worry about, we are restarting the "
                    "logfilter now.",
                    proc.returncode,
                )
        except Exception:
            logger.warning(
                "MENDIX LOGGING: Logging pipeline failed completely. To "
                "restore log availibility, restart your application.",
                exc_info=True,
            )


def set_up_logging_file():
    buildpackutil.lazy_remove_file("log/out.log")
    os.mkfifo("log/out.log")
    log_ratelimit = os.getenv("LOG_RATELIMIT", None)
    if log_ratelimit is None:
        subprocess.Popen(
            [
                "sed",
                "--unbuffered",
                "s|^[0-9\-]\+\s[0-9:\.]\+\s||",
                "log/out.log",
            ]
        )
    else:
        log_filter_thread = LogFilterThread(log_ratelimit)
        log_filter_thread.daemon = True
        log_filter_thread.start()


def service_backups():
    vcap_services = buildpackutil.get_vcap_services_data()
    schnapps = None
    amazon_s3 = None
    for key in vcap_services:
        if key.startswith("amazon-s3"):
            amazon_s3 = key
        if key.startswith("schnapps"):
            schnapps = key

    if not vcap_services or schnapps not in vcap_services:
        logger.debug("No backup service detected")
        return

    backup_service = {}
    if amazon_s3 in vcap_services:
        s3_credentials = vcap_services[amazon_s3][0]["credentials"]
        backup_service["filesCredentials"] = {
            "accessKey": s3_credentials["access_key_id"],
            "secretKey": s3_credentials["secret_access_key"],
            "bucketName": s3_credentials["bucket"],
        }
        if "key_suffix" in s3_credentials:  # Not all s3 plans have this field
            backup_service["filesCredentials"]["keySuffix"] = s3_credentials[
                "key_suffix"
            ]

    try:
        db_config = database_config.get_database_config()
        if db_config["DatabaseType"] != "PostgreSQL":
            raise Exception(
                "Schnapps only supports postgresql, not %s"
                % db_config["DatabaseType"]
            )
        host_and_port = db_config["DatabaseHost"].split(":")
        backup_service["databaseCredentials"] = {
            "host": host_and_port[0],
            "username": db_config["DatabaseUserName"],
            "password": db_config["DatabasePassword"],
            "dbname": db_config["DatabaseName"],
            "port": int(host_and_port[1]) if len(host_and_port) > 1 else 5432,
        }
    except Exception as e:
        logger.exception(
            "Schnapps will not be activated because error occurred with "
            "parsing the database credentials"
        )
        return
    schnapps_url = vcap_services[schnapps][0]["credentials"]["url"]
    schnapps_api_key = vcap_services[schnapps][0]["credentials"]["apiKey"]

    try:
        result = requests.put(
            schnapps_url,
            headers={
                "Content-Type": "application/json",
                "apiKey": schnapps_api_key,
            },
            data=json.dumps(backup_service),
        )
    except requests.exceptions.SSLError as e:
        logger.warning("Failed to contact backup service. SSLError: " + str(e))
        return
    except Exception as e:
        logger.warning("Failed to contact backup service: ", exc_info=True)
        return

    if result.status_code == 200:
        logger.info("Successfully updated backup service")
    else:
        logger.warning("Failed to update backup service: " + result.text)


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
                if i_am_primary_instance():
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


@atexit.register
def terminate_process():
    if m2ee:
        logger.info("stopping app...")
        if not m2ee.stop():
            if not m2ee.terminate():
                m2ee.kill()
    try:
        this_process = os.getpgid(0)
        logger.debug(
            "Terminating process group with pgid={}".format(this_process)
        )
        os.killpg(this_process, signal.SIGTERM)
        time.sleep(3)
        os.killpg(this_process, signal.SIGKILL)
    except Exception:
        logger.exception("Failed to terminate all child processes")


def create_admin_user(m2ee):
    logger.info("Ensuring admin user credentials")
    app_admin_password = get_admin_password()
    if os.getenv("M2EE_PASSWORD"):
        logger.debug(
            "M2EE_PASSWORD is set so skipping creation of application admin password"
        )
        return
    if not app_admin_password:
        logger.warning(
            "ADMIN_PASSWORD not set, so skipping creation of application admin password"
        )
        return
    logger.debug("Creating admin user")

    m2eeresponse = m2ee.client.create_admin_user(
        {"password": app_admin_password}
    )
    if m2eeresponse.has_error():
        m2eeresponse.display_error()
        if not is_development_mode():
            sys.exit(1)

    logger.debug("Setting admin user password")
    m2eeresponse = m2ee.client.create_admin_user(
        {
            "username": m2ee.config._model_metadata["AdminUser"],
            "password": app_admin_password,
        }
    )
    if m2eeresponse.has_error():
        m2eeresponse.display_error()
        if not is_development_mode():
            sys.exit(1)


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
        logger.debug("The password to use is {}".format(debugger_password))
        logger.info(
            "You can use the remote debugger option in the Mendix "
            "Business Modeler to connect to the /debugger/ sub "
            "url on your application (e.g. "
            "https://app.example.com/debugger/). "
        )


def _transform_logging(nodes):
    res = []
    for k, v in nodes.items():
        res.append({"name": k, "level": v})
    return res


def configure_logging(m2ee):
    for k, v in os.environ.items():
        if k.startswith("LOGGING_CONFIG"):
            m2ee.set_log_levels(
                "*", nodes=_transform_logging(json.loads(v)), force=True
            )


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


def display_running_version(m2ee):
    if m2ee.config.get_runtime_version() >= 4.4:
        feedback = m2ee.client.about().get_feedback()
        if "model_version" in feedback:
            logger.info("Model version: %s" % feedback["model_version"])


def loop_until_process_dies(m2ee):
    while True:
        if app_is_restarting or m2ee.runner.check_pid():
            time.sleep(10)
        else:
            break
    emit(jvm={"crash": 1.0})
    logger.info("process died, stopping")
    sys.exit(1)


def set_up_instadeploy_if_deploy_password_is_set(m2ee):
    if os.getenv("DEPLOY_PASSWORD"):
        mx_version = m2ee.config.get_runtime_version()
        if use_instadeploy(mx_version):

            def reload_callback():
                m2ee.client.request("reload_model")

            def restart_callback():
                global app_is_restarting
                app_is_restarting = True
                if not m2ee.stop():
                    m2ee.terminate()
                complete_start_procedure_safe_to_use_for_restart(m2ee)
                app_is_restarting = False

            thread = instadeploy.InstaDeployThread(
                get_deploy_port(),
                restart_callback,
                reload_callback,
                mx_version,
            )
            thread.setDaemon(True)
            thread.start()

            if os.path.exists(os.path.expanduser("~/.sourcepush")):
                instadeploy.send_metadata_to_cloudportal()
        else:
            logger.warning(
                "Not setting up InstaDeploy because this mendix "
                "runtime version %s does not support it" % mx_version
            )


def start_metrics(m2ee):
    metrics_interval = os.getenv("METRICS_INTERVAL")
    if metrics_interval:
        import metrics

        if buildpackutil.is_free_app():
            thread = metrics.FreeAppsMetricsEmitterThread(
                int(metrics_interval), m2ee
            )
        else:
            thread = metrics.PaidAppsMetricsEmitterThread(
                int(metrics_interval), m2ee
            )
        thread.setDaemon(True)
        thread.start()
    else:
        logger.info("MENDIX-INTERNAL: Metrics are disabled.")


class LoggingHeartbeatEmitterThread(threading.Thread):
    def __init__(self, interval):
        super().__init__()
        self.interval = interval

    def run(self):
        logger.debug(
            "Starting metrics emitter with interval %d", self.interval
        )
        counter = 1
        while True:
            logger.info(
                "MENDIX-LOGGING-HEARTBEAT: Heartbeat number %s", counter
            )
            time.sleep(self.interval)
            counter += 1


def start_logging_heartbeat():
    logging_interval = os.getenv(
        "METRICS_LOGGING_HEARTBEAT_INTERVAL", str(3600)
    )
    thread = LoggingHeartbeatEmitterThread(int(logging_interval))
    thread.setDaemon(True)
    thread.start()


def complete_start_procedure_safe_to_use_for_restart(m2ee):
    display_java_version()
    buildpackutil.mkdir_p("model/lib/userlib")
    set_up_logging_file()
    start_app(m2ee)
    create_admin_user(m2ee)
    configure_logging(m2ee)
    display_running_version(m2ee)
    configure_debugger(m2ee)


if __name__ == "__main__":
    if os.getenv("CF_INSTANCE_INDEX") is None:
        logger.warning(
            "CF_INSTANCE_INDEX environment variable not found. Assuming "
            "responsibility for scheduled events execution and database "
            "synchronization commands."
        )
    pre_process_m2ee_yaml()
    activate_license()
    m2ee = set_up_m2ee_client(buildpackutil.get_vcap_data())

    def sigterm_handler(_signo, _stack_frame):
        m2ee.stop()
        sys.exit(0)

    def sigusr_handler(_signo, _stack_frame):
        if _signo == signal.SIGUSR1:
            emit(jvm={"errors": 1.0})
        elif _signo == signal.SIGUSR2:
            emit(jvm={"ooms": 1.0})
        else:
            # Should not happen
            pass
        m2ee.stop()
        sys.exit(1)

    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGUSR1, sigusr_handler)
    signal.signal(signal.SIGUSR2, sigusr_handler)

    try:
        service_backups()
        set_up_nginx_files(m2ee)
        telegraf.run()
        datadog.run()
        complete_start_procedure_safe_to_use_for_restart(m2ee)
        set_up_instadeploy_if_deploy_password_is_set(m2ee)
        start_metrics(m2ee)
        start_logging_heartbeat()
        start_nginx()
        loop_until_process_dies(m2ee)
    except Exception:
        x = traceback.format_exc()
        logger.error("Starting app container failed: %s" % x)
        callback_url = os.environ.get("BUILD_STATUS_CALLBACK_URL")
        if callback_url:
            requests.put(callback_url, x)
        raise
