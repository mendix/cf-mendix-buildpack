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


def _should_use_license_server():
    use_license_server = os.environ.get("MXRUNTIME_License.UseLicenseServer", "").lower()
    return use_license_server == "true"


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


def _download_sap_sidecar(build_path, endpoint, token):
    """Download SAP metering sidecar binary from HTTPS endpoint."""
    import requests

    logging.info("=== SAP METERING SIDECAR DOWNLOAD ===")

    # Reuse existing variables - same directory structure as Mendix sidecar
    sidecar_dir = os.path.join(build_path, NAMESPACE)
    destination = os.path.join(sidecar_dir, BINARY)

    logging.info("Source endpoint: %s", endpoint)
    logging.info("Target directory: %s", sidecar_dir)
    logging.info("Target file: %s", destination)

    util.mkdir_p(sidecar_dir)
    logging.info("Created target directory: %s", sidecar_dir)

    logging.info("Downloading SAP metering sidecar from [%s]...", endpoint)

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

    logging.info("SAP metering sidecar downloaded successfully to [%s]", destination)

    # Verify file exists and get size
    if os.path.exists(destination):
        file_size = os.path.getsize(destination)
        logging.info("Binary file size: %.2f MB", file_size / (1024 * 1024))
    else:
        logging.error("Binary file not found after download: %s", destination)
        raise Exception(f"Binary file not found: {destination}")

    util.set_executable(destination)
    logging.info("Set executable permissions for: %s", BINARY)

    logging.info("=== SAP METERING SIDECAR DOWNLOAD COMPLETE ===")
    return destination


def stage(buildpack_path, build_path, cache_dir):
    if _should_use_license_server():
        # UseLicenseServer = true: original Mendix metering flow
        try:
            if _is_usage_metering_enabled():
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
            else:
                logging.info("Usage metering is NOT enabled")
        except Exception:
            logging.info(
                "Encountered an exception while staging the metering sidecar. "
                "This is nothing to worry about."
            )
    else:
        # UseLicenseServer = false: attempt SAP metering sidecar download
        endpoint = _get_sap_metering_endpoint()
        token = _get_sap_metering_token()

        if not endpoint or not token:
            logging.warning(
                "SAP metering sidecar NOT downloaded: "
                "MXRUNTIME_License.MeteringEndpoint or MXRUNTIME_License.MeteringToken "
                "is missing or empty. Continuing buildpack execution."
            )
            return

        try:
            _download_sap_sidecar(build_path, endpoint, token)
            logging.info("SAP metering sidecar staged successfully")
        except Exception:
            logging.error(
                "Encountered an exception while staging the SAP metering sidecar. "
                "Continuing buildpack execution.",
                exc_info=True,
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
