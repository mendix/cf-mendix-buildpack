import json
import logging

import requests

from buildpack import util
from buildpack.runtime_components import database


def run():
    vcap_services = util.get_vcap_services_data()
    schnapps = None
    amazon_s3 = None
    for key in vcap_services:
        if key.startswith("amazon-s3"):
            amazon_s3 = key
        if key.startswith("schnapps"):
            schnapps = key

    if not vcap_services or schnapps not in vcap_services:
        logging.debug("No backup service detected")
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
        db_config = database.get_config()
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
        logging.exception(
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
        logging.warning(
            "Failed to contact backup service. SSLError: %s", str(e)
        )
        return
    except Exception as e:
        logging.warning("Failed to contact backup service: ", exc_info=True)
        return

    if result.status_code == 200:
        logging.info("Successfully updated backup service")
    else:
        logging.warning("Failed to update backup service: " + result.text)
