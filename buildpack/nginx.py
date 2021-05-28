import crypt
import distutils
import json
import logging
import os
import re
import shutil
import subprocess

from buildpack import util
from buildpack.runtime_components import security
from lib.m2ee.version import MXVersion

from jinja2 import Template

DEFAULT_HEADERS = {
    "X-Frame-Options": r"(?i)(^allow-from https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$|^deny$|^sameorigin$)",  # noqa: E501
    "Referrer-Policy": r"(?i)(^no-referrer$|^no-referrer-when-downgrade$|^origin|origin-when-cross-origin$|^same-origin|strict-origin$|^strict-origin-when-cross-origin$|^unsafe-url$)",  # noqa: E501
    "Access-Control-Allow-Origin": r"(?i)(^\*$|^null$|^https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$)",  # noqa: E501
    "X-Content-Type-Options": r"(?i)(^nosniff$)",
    "Content-Security-Policy": r"[a-zA-Z0-9:;/''\"\*_\- \.\n?=%&]+",
    "X-Permitted-Cross-Domain-Policies": r"(?i)(^all$|^none$|^master-only$|^by-content-type$|^by-ftp-filename$)",  # noqa: E501
    "X-XSS-Protection": r"(?i)(^0$|^1$|^1; mode=block$|^1; report=https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$)",  # noqa: E501
}

CONFIG_FILE = "nginx/conf/nginx.conf"
PROXY_FILE = "nginx/conf/proxy_params"


# Fix for Chrome SameSite enforcement (from Chrome 80 onwards)
# Runtime will set this cookie in runtime versions >= SAMESITE_COOKIE_WORKAROUND_LESS_MX_VERSION


def _is_samesite_cookie_workaround_enabled(mx_version):
    SAMESITE_COOKIE_WORKAROUND_ENV_KEY = "SAMESITE_COOKIE_PRE_MX812"
    SAMESITE_COOKIE_WORKAROUND_DEFAULT = False
    SAMESITE_COOKIE_WORKAROUND_LESS_MX_VERSION = "8.12"

    try:
        return distutils.util.strtobool(
            os.environ.get(
                SAMESITE_COOKIE_WORKAROUND_ENV_KEY,
                str(SAMESITE_COOKIE_WORKAROUND_DEFAULT),
            )
        ) and mx_version < MXVersion(
            SAMESITE_COOKIE_WORKAROUND_LESS_MX_VERSION
        )
    except (ValueError, AttributeError):
        logging.warning(
            "Invalid value for [%s], disabling SameSite cookie workaround",
            SAMESITE_COOKIE_WORKAROUND_ENV_KEY,
        )
        return False


def is_custom_nginx():
    if "NGINX_CUSTOM_BIN_PATH" in os.environ:
        return True


def stage(buildpack_path, build_path, cache_path):
    logging.debug("Staging nginx...")
    shutil.copytree(
        os.path.join(buildpack_path, "etc/nginx"),
        os.path.join(build_path, "nginx"),
    )

    if not is_custom_nginx():
        logging.debug("Downloading nginx...")
        util.download_and_unpack(
            util.get_blobstore_url(
                "/mx-buildpack/nginx_1.19.1_linux_x64_cflinuxfs3_b5af01b0.tgz"
            ),
            os.path.join(build_path, "nginx"),
            cache_dir=cache_path,
        )
    else:
        logging.debug(
            "Custom nginx path provided, nginx will not be downloaded"
        )


def configure(m2ee):
    samesite_cookie_workaround_enabled = _is_samesite_cookie_workaround_enabled(
        MXVersion(str(m2ee.config.get_runtime_version()))
    )
    if samesite_cookie_workaround_enabled:
        logging.info("SameSite cookie workaround is enabled")

    # Populating nginx config template
    output_path = os.path.abspath(CONFIG_FILE)
    template_path = os.path.abspath("{}.j2".format(CONFIG_FILE))

    with open(template_path, "r") as file_:
        template = Template(file_.read(), trim_blocks=True, lstrip_blocks=True)
    rendered = template.render(
        samesite_cookie_workaround_enabled=samesite_cookie_workaround_enabled,
        locations=get_access_restriction_locations(),
        default_headers=get_http_headers(),
        nginx_port=str(util.get_nginx_port()),
        runtime_port=str(util.get_runtime_port()),
        admin_port=str(util.get_admin_port()),
        root=os.getcwd(),
    )

    logging.debug("Writing nginx configuration file...")
    with open(output_path, "w") as file_:
        file_.write(rendered)
    logging.debug("nginx configuration file written")

    # Populating proxy params template
    output_path = os.path.abspath(PROXY_FILE)
    template_path = os.path.abspath("{}.j2".format(PROXY_FILE))

    with open(template_path, "r") as file_:
        template = Template(file_.read(), trim_blocks=True, lstrip_blocks=True)
    rendered = template.render(
        proxy_buffers=get_proxy_buffers(),
        proxy_buffer_size=get_proxy_buffer_size(),
    )

    logging.debug("Writing proxy_params configuration file...")
    with open(output_path, "w") as file_:
        file_.write(rendered)
    logging.debug("proxy_params configuration file written")

    generate_password_file({"MxAdmin": security.get_m2ee_password()})


def get_proxy_buffer_size():
    proxy_buffer_size = os.environ.get("NGINX_PROXY_BUFFER_SIZE", None)
    return proxy_buffer_size


def get_proxy_buffers():
    proxy_buffers = os.environ.get("NGINX_PROXY_BUFFERS", None)
    return proxy_buffers


def get_http_headers():
    headers_from_json = {}

    # this is kept for X-Frame-Options backward compatibility
    x_frame_options = os.environ.get("X_FRAME_OPTIONS", "ALLOW")
    if x_frame_options != "ALLOW":
        headers_from_json["X-Frame-Options"] = x_frame_options

    headers_json = os.environ.get("HTTP_RESPONSE_HEADERS", "{}")

    try:
        headers_from_json.update(json.loads(headers_json))
    except Exception as _:
        logging.error(
            "Failed to parse HTTP_RESPONSE_HEADERS due to invalid JSON string: '%s'",
            headers_json,
        )
        raise

    result = []
    for header_key, header_value in headers_from_json.items():
        regEx = DEFAULT_HEADERS[header_key]
        if regEx and re.match(regEx, header_value):
            escaped_value = header_value.replace('"', '\\"').replace(
                "'", "\\'"
            )
            result.append((header_key, escaped_value))
            logging.debug(
                "Added header {} '{}' to nginx config".format(
                    header_key, header_value
                )
            )
        else:
            logging.warning(
                "Skipping {} config, value '{}' is not valid".format(
                    header_key, header_value
                )
            )

    return result


def get_nginx_bin_path():
    nginx_bin_path = os.environ.get(
        "NGINX_CUSTOM_BIN_PATH", "nginx/sbin/nginx"
    )
    return nginx_bin_path


def run():
    nginx_process = subprocess.Popen(
        [
            get_nginx_bin_path(),
            "-p",
            "nginx",
            "-c",
            str(os.path.abspath(CONFIG_FILE)),
        ]
    )
    return nginx_process


def generate_password_file(users_passwords, file_name_suffix=""):
    with open("nginx/.htpasswd" + file_name_suffix, "w") as fh:
        for user, password in users_passwords.items():
            if not password:
                fh.write("\n")
            else:
                fh.write(
                    "%s:%s\n"
                    % (
                        user,
                        crypt.crypt(
                            password, crypt.mksalt(crypt.METHOD_SHA512)
                        ),
                    )
                )


class Location:
    def __init__(self):
        self.path = None
        self.index = None
        self.proxy_buffering_enabled = True
        self.proxy_intercept_errors_enabled = False
        self.satisfy = "any"
        self.ipfilter_ips = None
        self.basic_auth_enabled = False
        self.client_cert_enabled = False
        self.issuer_dn_regex = None


def get_access_restriction_locations():
    # Example for ACCESS_RESTRICTIONS
    # {
    #     "/": {'ipfilter': ['10.0.0.0/8'], 'client_cert': true, 'satisfy': 'any'},
    #     "/ws/MyWebService/": {'ipfilter': ['10.0.0.0/8'], 'client_cert': true, 'satisfy': 'all'},
    #     "/CustomRequestHandler/": {'ipfilter': ['10.0.0.0/8']},
    #     "/CustomRequestHandler2/": {'basic_auth': {'user1': 'password', 'user2': 'password2'}},
    # }
    # Default for satisfy is any

    restrictions = json.loads(os.environ.get("ACCESS_RESTRICTIONS", "{}"))
    if "/file" not in restrictions:
        restrictions["/file"] = {}
    if "/" not in restrictions:
        restrictions["/"] = {}

    index = 0
    result = []

    for path, config in restrictions.items():
        location = Location()
        location.path = path
        location.index = index

        if path in ["/_mxadmin/"] or "/client-cert-check-internal" in path:
            raise Exception(
                "Can not override access restrictions on system path %s" % path
            )
        if path in ["/file"]:
            location.proxy_buffering_enabled = False
            location.proxy_intercept_errors_enabled = True
        if path in [
            "/",
            "/p/",
            "/rest-doc/",
            "/link/",
            "/api-doc/",
            "/odata-doc/",
            "/ws-doc/",
            "/rest-doc",
        ]:
            location.proxy_intercept_errors_enabled = True

        if "satisfy" in config:
            if config["satisfy"] in ["any", "all"]:
                location.satisfy = config["satisfy"]
            else:
                raise Exception(
                    "Invalid satisfy value: %s" % config["satisfy"]
                )

        if "ipfilter" in config:
            location.ipfilter_ips = []
            for ip in config["ipfilter"]:
                location.ipfilter_ips.append(ip)

        if "basic_auth" in config:
            location.basic_auth_enabled = True
            generate_password_file(config["basic_auth"], str(index))

        if config.get("client-cert") or config.get("client_cert"):
            location.client_cert_enabled = True

        # This scenario isn't covered by integration tests. Please test manually if Nginx is properly matching the
        # SSL-Client-I-DN HTTP header with the configuration in the ACCESS_RESTRICTIONS environment variable.
        if "issuer_dn" in config:
            location.issuer_dn_regex = ""
            location.issuer_dn = ""
            for i in config["issuer_dn"]:
                # Workaround for missing identifier strings from Java
                # This should be fixed in upstream code by using different certificate libraries
                issuer = i.replace("OID.2.5.4.97", "organizationIdentifier")

                location.issuer_dn += "{}|".format(issuer)

                # Escape special characters
                issuer = issuer.replace(" ", "\\040")
                issuer = issuer.replace(".", "\\.")
                issuer = issuer.replace("'", "\\'")

                location.issuer_dn_regex += "{}|".format(issuer)
            location.issuer_dn = location.issuer_dn[:-1]
            location.issuer_dn_regex = location.issuer_dn_regex[:-1]

        result.append(location)
        index += 1

    return result
