import json
import logging
import re
import os
import requests
import time
from buildpack import util
from lib.m2ee.version import MXVersion


def _get_s3_specific_config(vcap_services, m2ee):
    access_key = secret = bucket = encryption_keys = key_suffix = None
    tvm_endpoint = tvm_username = tvm_password = endpoint = amazon_s3 = None
    v2_auth = ""

    blobstore_type = os.getenv("MENDIX_BLOBSTORE_TYPE")

    for key in vcap_services:
        if key.startswith("amazon-s3") or (
            key == "objectstore"
            and (blobstore_type is None or blobstore_type == "s3")
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

    dont_perform_deletes = (
        os.getenv("S3_PERFORM_DELETES", "true").lower() == "false"
    )
    key_suffix = os.getenv("S3_KEY_SUFFIX", key_suffix)
    endpoint = os.getenv("S3_ENDPOINT", endpoint)
    v2_auth = os.getenv("S3_USE_V2_AUTH", v2_auth).lower() == "true"
    sse = os.getenv("S3_USE_SSE", "").lower() == "true"

    if not bucket:
        return None

    if access_key and secret:
        logging.info("S3 config detected, activating external file store")
        config = {
            "com.mendix.core.StorageService": "com.mendix.storage.s3",
            "com.mendix.storage.s3.AccessKeyId": access_key,
            "com.mendix.storage.s3.SecretAccessKey": secret,
            "com.mendix.storage.s3.BucketName": bucket,
        }
    elif (
        tvm_endpoint
        and tvm_username
        and tvm_password
        and (
            m2ee.config.get_runtime_version() >= 9.2
            or (
                m2ee.config.get_runtime_version() >= MXVersion("8.18.7")
                and m2ee.config.get_runtime_version() < 9
            )
            or (
                m2ee.config.get_runtime_version() >= MXVersion("7.23.22")
                and m2ee.config.get_runtime_version() < 8
            )
        )
    ):
        logging.info("S3 TVM config detected, activating external file store")
        config = {
            "com.mendix.core.StorageService": "com.mendix.storage.s3",
            "com.mendix.storage.s3.tokenService.Url": "https://%s/v1/gettoken"
            % tvm_endpoint,
            "com.mendix.storage.s3.tokenService.Username": tvm_username,
            "com.mendix.storage.s3.tokenService.Password": tvm_password,
            "com.mendix.storage.s3.tokenService.RefreshPercentage": 80,
            "com.mendix.storage.s3.tokenService.RetryIntervalInSeconds": 10,
            "com.mendix.storage.s3.BucketName": bucket,
        }
    elif tvm_endpoint and tvm_username and tvm_password:
        logging.info(
            "S3 TVM config detected, fetching IAM credentials from TVM"
        )
        access_key, secret = _get_credentials_from_tvm(
            tvm_endpoint, tvm_username, tvm_password, m2ee
        )
        config = {
            "com.mendix.core.StorageService": "com.mendix.storage.s3",
            "com.mendix.storage.s3.AccessKeyId": access_key,
            "com.mendix.storage.s3.SecretAccessKey": secret,
            "com.mendix.storage.s3.BucketName": bucket,
        }
    else:
        return None

    if dont_perform_deletes:
        logging.debug("disabling perform deletes for runtime")
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
    if m2ee.config.get_runtime_version() >= 6 and encryption_keys:
        config["com.mendix.storage.s3.EncryptionKeys"] = encryption_keys
    if m2ee.config.get_runtime_version() >= 6 and sse:
        config["com.mendix.storage.s3.UseSSE"] = sse
    return config


def _get_credentials_from_tvm(tvm_endpoint, tvm_username, tvm_password, m2ee):
    retry = 3
    while True:
        response = requests.get(
            "https://%s/v1/getcredentials" % tvm_endpoint,
            headers={
                "User-Agent": "Mendix Buildpack {} (for Mendix {})".format(
                    util.get_buildpack_version(),
                    m2ee.config.get_runtime_version(),
                )
            },
            auth=(tvm_username, tvm_password),
        )

        if response.ok:
            break
        elif not response.ok and retry == 0:
            logging.error("Failed to get IAM credential from TVM")
            raise Exception(
                "failed to get IAM credential from TVM for tvm_user %s"
                % tvm_username
            )
        else:
            retry = retry - 1
            time.sleep(5)
            logging.error(
                "Failed to get IAM credential from TVM (HTTP {}), Retrying... {}".format(
                    response.status_code, retry
                )
            )
            logging.error("Number of retries left = {}".format(retry))

    result = response.json()
    if "AccessKeyId" not in result:
        raise Exception(
            "failed to get IAM credential from TVM for tvm_user %s (missing AccessKeyId)"
            % tvm_username
        )
    if "SecretAccessKey" not in result:
        raise Exception(
            "failed to get IAM credential from TVM for tvm_user %s (missing SecretAccessKey)"
            % tvm_username
        )

    return result["AccessKeyId"], result["SecretAccessKey"]


def _get_swift_specific_config(vcap_services, m2ee):
    if "Object-Storage" not in vcap_services:
        return None

    if m2ee.config.get_runtime_version() < 6.7:
        logging.warning("Can not configure Object Storage with Mendix < 6.7")
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
    azure_storage = None

    for key in vcap_services:
        if key.startswith("azure-storage") or (
            key == "objectstore"
            and os.getenv("MENDIX_BLOBSTORE_TYPE") == "azure"
        ):
            azure_storage = vcap_services[key][0]

    if azure_storage:
        if m2ee.config.get_runtime_version() < 6.7:
            logging.warning(
                "Can not configure Azure Storage with Mendix < 6.7"
            )
            return None

        creds = azure_storage["credentials"]

        container_name = os.getenv("AZURE_CONTAINER_NAME", "mendix")

        config_object = {
            "com.mendix.core.StorageService": "com.mendix.storage.azure",
            "com.mendix.storage.azure.Container": container_name,
            "com.mendix.storage.azure.CreateContainerIfNotExists": False,
        }

        if "primary_access_key" in creds:
            config_object["com.mendix.storage.azure.AccountKey"] = creds[
                "primary_access_key"
            ]

        if "storage_account_name" in creds:
            config_object["com.mendix.storage.azure.AccountName"] = creds[
                "storage_account_name"
            ]

        if "account_name" in creds:
            config_object["com.mendix.storage.azure.AccountName"] = creds[
                "account_name"
            ]

        if "sas_token" in creds:
            config_object[
                "com.mendix.storage.azure.SharedAccessSignature"
            ] = creds["sas_token"]

        if "container_uri" in creds:
            config_object["com.mendix.storage.azure.BlobEndpoint"] = creds[
                "container_uri"
            ]

        if "container_name" in creds:
            config_object["com.mendix.storage.azure.Container"] = creds[
                "container_name"
            ]

        return config_object
    else:
        return None


def get_config(m2ee):
    vcap_services = util.get_vcap_services_data()

    config = _get_s3_specific_config(vcap_services, m2ee)

    if config is None:
        config = _get_swift_specific_config(vcap_services, m2ee)

    if config is None:
        config = _get_azure_storage_specific_config(vcap_services, m2ee)

    if config is None:
        logging.warning(
            "External file store not configured, uploaded files in the app "
            "will not persist across restarts. See https://github.com/mendix/"
            "cf-mendix-buildpack for file store configuration details."
        )
        return {}
    else:
        return config
