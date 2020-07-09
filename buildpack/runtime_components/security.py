import base64
import json
import logging
import os
import sys
import uuid

from lib.m2ee.version import MXVersion


def get_admin_password():
    return os.getenv("ADMIN_PASSWORD")


def get_m2ee_password(
    default_m2ee_password=str(uuid.uuid4()).replace("-", "@") + "A1"
):
    m2ee_password = os.getenv("M2EE_PASSWORD", get_admin_password())
    if not m2ee_password:
        logging.debug(
            "No ADMIN_PASSWORD or M2EE_PASSWORD configured, "
            "using a random password for the m2ee admin api"
        )
        m2ee_password = default_m2ee_password
    return m2ee_password


def create_admin_user(m2ee, is_development_mode):
    logging.info("Ensuring admin user credentials")
    app_admin_password = get_admin_password()
    if os.getenv("M2EE_PASSWORD"):
        logging.debug(
            "M2EE_PASSWORD is set so skipping creation of application admin password"
        )
        return
    if not app_admin_password:
        logging.warning(
            "ADMIN_PASSWORD not set, so skipping creation of application admin password"
        )
        return
    logging.debug("Creating admin user")

    m2eeresponse = m2ee.client.create_admin_user(
        {"password": app_admin_password}
    )
    if m2eeresponse.has_error():
        m2eeresponse.display_error()
        if not is_development_mode:
            sys.exit(1)

    logging.debug("Setting admin user password")
    m2eeresponse = m2ee.client.create_admin_user(
        {
            "username": m2ee.config._model_metadata["AdminUser"],
            "password": app_admin_password,
        }
    )
    if m2eeresponse.has_error():
        m2eeresponse.display_error()
        if not is_development_mode:
            sys.exit(1)


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


def get_client_certificates(mx_version):
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
        if mx_version < MXVersion("7.20"):
            logging.debug(
                "Runtime version < 7.20, using WebServiceClientCertificates..."
            )
            config["WebServiceClientCertificates"] = pins
        else:
            # Deprecated in 7.20
            logging.debug(
                "Runtime version >= 7.20, using ClientCertificateUsages..."
            )
            config["ClientCertificateUsages"] = pins
    return config
