import logging
import os
import json
import subprocess

from buildpack import util
from buildpack.infrastructure import database

NAMESPACE = "metering"
BINARY = "metering-sidecar"
DEPENDENCY = f"{NAMESPACE}.sidecar"
SIDECAR_DIR = os.path.join("/home/vcap/app", NAMESPACE)
SIDECAR_CONFIG_FILE = "conf.json"


def _download(buildpack_dir, build_path, cache_dir):
    util.resolve_dependency(
        DEPENDENCY,
        os.path.join(build_path, NAMESPACE),
        buildpack_dir=buildpack_dir,
        cache_dir=cache_dir,
    )


def _is_usage_metering_enabled():
    if "MXUMS_LICENSESERVER_URL" in os.environ:
        return True


def _is_sap_metering_configured():
    use_license_server = os.environ.get("MXRUNTIME_License.UseLicenseServer", "false").lower()
    if use_license_server == "true":
        return False
    
    endpoint = _get_sap_metering_endpoint()
    token = _get_sap_metering_token()

    if not endpoint or not token:
        logging.warning(
            "Missing configuration for SAP metering sidecar."
        )
        return False

    return True


def _get_sap_metering_endpoint():
    return os.environ.get("MXRUNTIME_License.MeteringEndpoint", "").strip() or None


def _get_sap_metering_token():
    return os.environ.get("MXRUNTIME_License.MeteringToken", "").strip() or None


def _get_project_id(file_path):
    try:
        with open(file_path) as file_handle:
            data = json.loads(file_handle.read())
            return data["ProjectID"]
    except IOError as ioerror:
        raise Exception(
            f"Error while trying to get the ProjectID. Reason: '{ioerror}'"
        ) from ioerror


def write_file(output_file_path, content):
    if output_file_path is None:
        print(content)
    else:
        try:
            with open(output_file_path, "w") as f:
                json.dump(content, f)
        except Exception as exception:
            raise Exception(
                f"Error while trying to write the configuration to a file. Reason: '{exception}'"  # noqa: C0301
            ) from exception


def _set_up_environment():
    if "MXRUNTIME_License.SubscriptionSecret" in os.environ:
        os.environ["MXUMS_SUBSCRIPTION_SECRET"] = os.environ[
            "MXRUNTIME_License.SubscriptionSecret"
        ]
    if "MXRUNTIME_License.LicenseServerURL" in os.environ:
        os.environ["MXUMS_LICENSESERVER_URL"] = os.environ[
            "MXRUNTIME_License.LicenseServerURL"
        ]
    if "MXRUNTIME_License.EnvironmentName" in os.environ:
        os.environ["MXUMS_ENVIRONMENT_NAME"] = os.environ[
            "MXRUNTIME_License.EnvironmentName"
        ]
    dbconfig = database.get_config()
    if dbconfig:
        os.environ["MXUMS_DB_CONNECTION_URL"] = (
            f"postgres://{dbconfig['DatabaseUserName']}:"
            f"{dbconfig['DatabasePassword']}@"
            f"{dbconfig['DatabaseHost']}/"
            f"{dbconfig['DatabaseName']}"
        )
    project_id = _get_project_id(os.path.join(SIDECAR_DIR, SIDECAR_CONFIG_FILE))
    os.environ["MXUMS_PROJECT_ID"] = project_id
    e = dict(os.environ.copy())
    return e


def _is_sidecar_installed():
    if os.path.exists(os.path.join(SIDECAR_DIR, BINARY)):
        if os.path.exists(os.path.join(SIDECAR_DIR, SIDECAR_CONFIG_FILE)):
            return True
        else:
            logging.info("Metering sidecar configuration not found")
    else:
        logging.info("Metering sidecar not found")
    return False


def _copy_sap_metering_sidecar(build_path, endpoint, token):
    """Download SAP metering sidecar binary from HTTPS endpoint."""
    import requests

    sidecar_dir = os.path.join(build_path, NAMESPACE)
    destination = os.path.join(sidecar_dir, BINARY)
    util.mkdir_p(sidecar_dir)

    # Download binary file via HTTPS with auth-token header
    response = requests.get(
        endpoint,
        headers={"auth-token": token},
        stream=True,
        timeout=60,
    )
    response.raise_for_status()

    # Stream binary content to disk
    with open(destination, "wb") as file_handle:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file_handle.write(chunk)

    logging.info("SAP metering sidecar downloaded successfully")
    util.set_executable(destination)
    return destination


def stage(buildpack_path, build_path, cache_dir):
    try:
        if _is_usage_metering_enabled():
            # Original Mendix metering flow
            logging.info("Usage metering is enabled")
            _download(buildpack_path, build_path, cache_dir)

            project_id = _get_project_id(
                os.path.join(build_path, "model", "metadata.json")
            )
            config = {"ProjectID": project_id}

            logging.debug("Writing metering sidecar configuration file...")
            write_file(
                os.path.join(build_path, NAMESPACE, SIDECAR_CONFIG_FILE),
                config,
            )
        elif _is_sap_metering_configured():
            # UseLicenseServer = false with valid SAP endpoint and token
            endpoint = _get_sap_metering_endpoint()
            token = _get_sap_metering_token()
            try:
                _copy_sap_metering_sidecar(build_path, endpoint, token)
                logging.info("SAP metering sidecar staged successfully")
            except Exception:
                logging.error(
                    "Encountered an exception while staging the SAP metering sidecar. "
                    "Continuing buildpack execution."
                )
                logging.debug("SAP metering sidecar staging exception details:", exc_info=True)
        else:
            logging.info("Usage metering is NOT enabled")
    except Exception:
        logging.info(
            "Encountered an exception while staging the metering sidecar. "
            "This is nothing to worry about."
        )


def run():
    try:
        if _is_usage_metering_enabled() and _is_sidecar_installed():
            logging.info("Starting metering sidecar")
            subprocess.Popen(
                os.path.join(SIDECAR_DIR, BINARY),
                env=_set_up_environment(),
            )
    except Exception:
        logging.info(
            "Encountered an exception while starting the metering sidecar."
            "This is nothing to worry about."
        )
