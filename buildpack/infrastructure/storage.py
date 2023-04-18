import json
import logging
import os
import re
import time

import requests
from buildpack import util
from buildpack.core import runtime
from lib.m2ee.version import MXVersion


STORAGE_CORE_CUSTOM_RUNTIME_SETTINGS_KEY = "com.mendix.core.StorageService"
STORAGE_CUSTOM_RUNTIME_SETTINGS_PREFIX = "com.mendix.storage."


def _get_s3_specific_config(vcap_services):
    version = runtime.get_runtime_version()
    access_key = secret = bucket = encryption_keys = key_suffix = None
    tvm_endpoint = tvm_username = tvm_password = endpoint = amazon_s3 = None
    v2_auth = ""

    blobstore_type = os.getenv("MENDIX_BLOBSTORE_TYPE")

    for key in vcap_services:
        if key.startswith("amazon-s3") or (
            key == "objectstore" and (blobstore_type is None or blobstore_type == "s3")
        ):
            amazon_s3 = key

    if amazon_s3:
        _conf = vcap_services[amazon_s3][0]["credentials"]
        bucket = _conf["bucket"]  # see below at hacky for actual conf
        if "access_key_id" in _conf:
            access_key = _conf["access_key_id"]
        if "secret_access_key" in _conf:
            secret = _conf["secret_access_key"]
        if "tvm_endpoint" in _conf:
            tvm_endpoint = _conf["tvm_endpoint"]
        if "tvm_username" in _conf:
            tvm_username = _conf["tvm_username"]
        if "tvm_password" in _conf:
            tvm_password = _conf["tvm_password"]
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
    tvm_endpoint = os.getenv("S3_TVM_ENDPOINT", tvm_endpoint)
    tvm_username = os.getenv("S3_TVM_USERNAME", tvm_username)
    tvm_password = os.getenv("S3_TVM_PASSWORD", tvm_password)
    bucket = os.getenv("S3_BUCKET_NAME", bucket)
    if "S3_ENCRYPTION_KEYS" in os.environ:
        encryption_keys = json.loads(os.getenv("S3_ENCRYPTION_KEYS"))

    dont_perform_deletes = os.getenv("S3_PERFORM_DELETES", "true").lower() == "false"
    key_suffix = os.getenv("S3_KEY_SUFFIX", key_suffix)
    endpoint = os.getenv("S3_ENDPOINT", endpoint)
    v2_auth = os.getenv("S3_USE_V2_AUTH", v2_auth).lower() == "true"
    sse = os.getenv("S3_USE_SSE", "").lower() == "true"

    if not bucket:
        return None

    core_config_value = STORAGE_CUSTOM_RUNTIME_SETTINGS_PREFIX + "s3"
    config_prefix = core_config_value + "."
    if access_key and secret:
        logging.info("S3 config detected, activating external file store")
        config = {
            STORAGE_CORE_CUSTOM_RUNTIME_SETTINGS_KEY: core_config_value,
            config_prefix + "AccessKeyId": access_key,
            config_prefix + "SecretAccessKey": secret,
            config_prefix + "BucketName": bucket,
        }
    elif (
        tvm_endpoint and tvm_username and tvm_password and _runtime_sts_support(version)
    ):
        logging.info("S3 TVM config detected")
        config = {
            STORAGE_CORE_CUSTOM_RUNTIME_SETTINGS_KEY: core_config_value,
            config_prefix + "tokenService.Url": f"https://{tvm_endpoint}/v1/gettoken",
            config_prefix + "tokenService.Username": tvm_username,
            config_prefix + "tokenService.Password": tvm_password,
            config_prefix + "tokenService.RefreshPercentage": 80,
            config_prefix + "tokenService.RetryIntervalInSeconds": 10,
            config_prefix + "BucketName": bucket,
        }
    elif tvm_endpoint and tvm_username and tvm_password:
        logging.info("S3 TVM config detected, fetching IAM credentials from TVM...")
        access_key, secret = _get_credentials_from_tvm(
            tvm_endpoint, tvm_username, tvm_password
        )
        config = {
            STORAGE_CORE_CUSTOM_RUNTIME_SETTINGS_KEY: core_config_value,
            config_prefix + "AccessKeyId": access_key,
            config_prefix + "SecretAccessKey": secret,
            config_prefix + "BucketName": bucket,
        }
    else:
        return None

    if dont_perform_deletes:
        logging.debug("disabling perform deletes for runtime")
        if version < 7.19:
            # Deprecated in 7.19
            config[config_prefix + "PerformDeleteFromStorage"] = False
        elif version >= 9.12 or (
            version.major == 9 and version.minor == 6 and version.patch >= 11
        ):
            config[
                STORAGE_CUSTOM_RUNTIME_SETTINGS_PREFIX + "PerformDeleteFromStorage"
            ] = "NoFiles"
        else:
            config[
                STORAGE_CUSTOM_RUNTIME_SETTINGS_PREFIX + "PerformDeleteFromStorage"
            ] = False
    if key_suffix:
        config[config_prefix + "ResourceNameSuffix"] = key_suffix
    if v2_auth:
        config[config_prefix + "UseV2Auth"] = v2_auth
    if endpoint:
        config[config_prefix + "EndPoint"] = endpoint
    if version >= 6 and encryption_keys:
        config[config_prefix + "EncryptionKeys"] = encryption_keys
    if version >= 6 and sse:
        config[config_prefix + "UseSSE"] = sse
    return config


def _runtime_sts_support(version):
    if (
        version >= MXVersion("9.6.1")
        or (version.major == 8 and version >= MXVersion("8.18.11"))
        or (version.major == 7 and version >= MXVersion("7.23.30"))
    ):
        return True
    # Only enable STS support for these versions when CERTIFICATE_AUTHORITIES
    # is not set and CLIENT_CERTIFICATES is not set or STS will break.
    elif (
        (
            version >= 9.2
            or (version.major == 8 and version >= MXVersion("8.18.7"))
            or (version.major == 7 and version >= MXVersion("7.23.22"))
        )
        and not os.getenv("CERTIFICATE_AUTHORITIES", None)
        and not os.getenv("CLIENT_CERTIFICATES", None)
    ):
        return True
    else:
        return False


def _get_credentials_from_tvm(tvm_endpoint, tvm_username, tvm_password):
    retry = 3
    while True:
        response = requests.get(
            f"https://{tvm_endpoint}/v1/getcredentials",
            headers={
                "User-Agent": (
                    f"Mendix Buildpack {util.get_buildpack_version()} "
                    f"(for Mendix {runtime.get_runtime_version()})"
                )
            },
            auth=(tvm_username, tvm_password),
        )

        if 200 <= response.status_code <= 299:
            break
        if 400 <= response.status_code <= 499:
            message = response.content.decode("UTF-8").strip()
            try:
                message = json.loads(message)["Error"]["Message"]
            except Exception:
                pass

            logging.error(
                "Failed to get IAM credential from TVM (HTTP %d): %s",
                response.status_code,
                message,
            )
            raise Exception(
                f"failed to get IAM credential from TVM for tvm_user {tvm_username}"
            )
        else:
            retry = retry - 1
            time.sleep(5)
            logging.error(
                "Failed to get IAM credential from TVM (HTTP %d), Retrying... %d",
                response.status_code,
                retry,
            )
            logging.error("Number of retries left = %d", retry)
            if retry == 0:
                raise Exception(
                    f"failed to get IAM credential from TVM for tvm_user {tvm_username}"
                )

    result = response.json()
    if "AccessKeyId" not in result:
        raise Exception(
            f"failed to get IAM credential from TVM for tvm_user {tvm_username} "
            "(missing AccessKeyId)"
        )
    if "SecretAccessKey" not in result:
        raise Exception(
            f"failed to get IAM credential from TVM for tvm_user {tvm_username} "
            "(missing SecretAccessKey)"
        )

    return result["AccessKeyId"], result["SecretAccessKey"]


def _get_swift_specific_config(vcap_services):
    if "Object-Storage" not in vcap_services:
        return None

    if runtime.get_runtime_version() < 6.7:
        logging.warning("Can not configure Object Storage with Mendix < 6.7")
        return None

    creds = vcap_services["Object-Storage"][0]["credentials"]

    container_name = os.getenv("SWIFT_CONTAINER_NAME", "mendix")

    core_config_value = STORAGE_CUSTOM_RUNTIME_SETTINGS_PREFIX + "swift"
    config_prefix = core_config_value + "."
    return {
        STORAGE_CORE_CUSTOM_RUNTIME_SETTINGS_KEY: core_config_value,
        config_prefix + "Container": container_name,
        config_prefix + "Container.AutoCreate": True,
        config_prefix + "credentials.DomainId": creds["domainId"],
        config_prefix + "credentials.Authurl": creds["auth_url"],
        config_prefix + "credentials.Username": creds["username"],
        config_prefix + "credentials.Password": creds["password"],
        config_prefix + "credentials.Region": creds["region"],
    }


def _get_azure_storage_specific_config(vcap_services):
    azure_storage = None

    for key in vcap_services:
        if key.startswith("azure-storage") or (
            key == "objectstore" and os.getenv("MENDIX_BLOBSTORE_TYPE") == "azure"
        ):
            azure_storage = vcap_services[key][0]

    if azure_storage:
        if runtime.get_runtime_version() < 6.7:
            logging.warning("Can not configure Azure Storage with Mendix < 6.7")
            return None

        creds = azure_storage["credentials"]

        container_name = os.getenv("AZURE_CONTAINER_NAME", "mendix")

        core_config_value = STORAGE_CUSTOM_RUNTIME_SETTINGS_PREFIX + "azure"
        config_prefix = core_config_value + "."
        config_object = {
            STORAGE_CORE_CUSTOM_RUNTIME_SETTINGS_KEY: core_config_value,
            config_prefix + "Container": container_name,
            config_prefix + "CreateContainerIfNotExists": False,
        }

        if "primary_access_key" in creds:
            config_object[config_prefix + "AccountKey"] = creds["primary_access_key"]

        if "storage_account_name" in creds:
            config_object[config_prefix + "AccountName"] = creds["storage_account_name"]

        if "account_name" in creds:
            config_object[config_prefix + "AccountName"] = creds["account_name"]

        if "sas_token" in creds:
            config_object[config_prefix + "SharedAccessSignature"] = creds["sas_token"]

        if "container_uri" in creds:
            config_object[config_prefix + "BlobEndpoint"] = creds["container_uri"]

        if "container_name" in creds:
            config_object[config_prefix + "Container"] = creds["container_name"]

        return config_object
    return None


def _get_config_from_vcap():
    vcap_services = util.get_vcap_services_data()

    config = _get_s3_specific_config(vcap_services)

    if config is None:
        config = _get_swift_specific_config(vcap_services)

    if config is None:
        config = _get_azure_storage_specific_config(vcap_services)

    if config is None:
        return {}
    else:
        return config


def _is_user_defined_config(m2ee):
    keys = [x.lower() for x in util.get_custom_runtime_settings(m2ee).keys()]
    return any(
        x.startswith(STORAGE_CUSTOM_RUNTIME_SETTINGS_PREFIX.lower()) for x in keys
    ) or any(x == STORAGE_CORE_CUSTOM_RUNTIME_SETTINGS_KEY.lower() for x in keys)


def update_config(m2ee):
    is_user_defined_config = _is_user_defined_config(m2ee)
    vcap_config = _get_config_from_vcap()

    if is_user_defined_config:
        if len(vcap_config) > 0:
            logging.warning(
                "External file store service binding detected, "
                "but user-defined storage settings supplied."
            )
        logging.info(
            "Using external file store configured by user-defined settings. "
            "See https://github.com/mendix/cf-mendix-buildpack "
            "for file store configuration details."
        )
    else:
        if len(vcap_config) > 0:
            logging.info("Using external file store configured by service binding")
        else:
            logging.warning(
                "External file store not configured. "
                "Files stored by the application will not persist across restarts. "
                "See https://github.com/mendix/cf-mendix-buildpack "
                "for file store configuration details."
            )

    util.upsert_custom_runtime_settings(m2ee, vcap_config, overwrite=False, append=True)
