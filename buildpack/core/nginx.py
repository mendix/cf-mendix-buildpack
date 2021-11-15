import crypt
import distutils
import json
import logging
import os
import re
import shutil
import subprocess

from buildpack import util
from buildpack.core import runtime, security
from lib.m2ee.version import MXVersion

from jinja2 import Template

ALLOWED_HEADERS = {
    "X-Frame-Options": r"(?i)(^allow-from https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$|^deny$|^sameorigin$)",  # noqa: E501
    "Referrer-Policy": r"(?i)(^no-referrer$|^no-referrer-when-downgrade$|^origin|origin-when-cross-origin$|^same-origin|strict-origin$|^strict-origin-when-cross-origin$|^unsafe-url$)",  # noqa: E501
    "Access-Control-Allow-Origin": r"(?i)(^\*$|^null$|^https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$)",  # noqa: E501
    "X-Content-Type-Options": r"(?i)(^nosniff$)",
    "Content-Security-Policy": r"[a-zA-Z0-9:;/''\"\*_\- \.\n?=%&+]+",
    "X-Permitted-Cross-Domain-Policies": r"(?i)(^all$|^none$|^master-only$|^by-content-type$|^by-ftp-filename$)",  # noqa: E501
    "X-XSS-Protection": r"(?i)(^0$|^1$|^1; mode=block$|^1; report=https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$)",  # noqa: E501
}

CONFIG_FILE = "nginx/conf/nginx.conf"
PROXY_FILE = "nginx/conf/proxy_params"

DEFAULT_REQUEST_HANDLER_PATHS = [
    "/p/",
    "/rest-doc/",
    "/link/",
    "/api-doc/",
    "/odata-doc/",
    "/ws-doc/",
]
FILE_HANDLER_PATH = "/file"
DEFAULT_LOCATION_PATHS = ["/", FILE_HANDLER_PATH]
MXADMIN_PATH = "/_mxadmin/"
CLIENT_CERT_CHECK_INTERNAL_PATH_PREFIX = "/client-cert-check-internal"
RESERVED_PATH_PREFIXES = [MXADMIN_PATH, CLIENT_CERT_CHECK_INTERNAL_PATH_PREFIX]

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


def _is_custom_nginx():
    if "NGINX_CUSTOM_BIN_PATH" in os.environ:
        return True


def stage(buildpack_path, build_path, cache_path):
    logging.debug("Staging nginx...")
    shutil.copytree(
        os.path.join(buildpack_path, "etc/nginx"),
        os.path.join(build_path, "nginx"),
    )

    if not _is_custom_nginx():
        logging.debug("Downloading nginx...")
        util.resolve_dependency(
            util.get_blobstore_url(
                "/mx-buildpack/nginx_1.21.1_linux_x64_cflinuxfs3_f0918d6b.tgz"
            ),
            os.path.join(build_path, "nginx"),
            buildpack_dir=buildpack_path,
            cache_dir=cache_path,
        )
    else:
        logging.debug(
            "Custom nginx path provided, nginx will not be downloaded"
        )


def update_config():
    samesite_cookie_workaround_enabled = (
        _is_samesite_cookie_workaround_enabled(runtime.get_runtime_version())
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
        locations=_get_locations(),
        default_headers=_get_http_headers(),
        nginx_port=str(util.get_nginx_port()),
        runtime_port=str(util.get_runtime_port()),
        admin_port=str(util.get_admin_port()),
        root=os.getcwd(),
        mxadmin_path=MXADMIN_PATH,
        client_cert_check_internal_path_prefix=CLIENT_CERT_CHECK_INTERNAL_PATH_PREFIX,
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
        proxy_buffers=_get_proxy_buffers(),
        proxy_buffer_size=_get_proxy_buffer_size(),
    )

    logging.debug("Writing proxy_params configuration file...")
    with open(output_path, "w") as file_:
        file_.write(rendered)
    logging.debug("proxy_params configuration file written")

    _generate_password_file({"MxAdmin": security.get_m2ee_password()})


def _get_proxy_buffer_size():
    return os.environ.get("NGINX_PROXY_BUFFER_SIZE", None)


def _get_proxy_buffers():
    return os.environ.get("NGINX_PROXY_BUFFERS", None)


def _get_access_restrictions():
    return os.environ.get("ACCESS_RESTRICTIONS", "{}")


def _get_http_headers():
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
        regEx = ALLOWED_HEADERS[header_key]
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


def _get_nginx_bin_path():
    nginx_bin_path = os.environ.get(
        "NGINX_CUSTOM_BIN_PATH", "nginx/sbin/nginx"
    )
    return nginx_bin_path


def run():
    nginx_process = subprocess.Popen(
        [
            _get_nginx_bin_path(),
            "-p",
            "nginx",
            "-c",
            str(os.path.abspath(CONFIG_FILE)),
        ]
    )
    return nginx_process


def _generate_password_file(users_passwords, file_name_suffix=""):
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
        # General location parameters
        self.path = None
        self.index = None
        self.proxy_buffering_enabled = True
        self.proxy_intercept_errors_enabled = False

        # Access restriction parameters
        self.satisfy = "any"
        self.ipfilter_ips = None
        self.basic_auth_enabled = False
        self.client_cert_enabled = False
        self.issuer_dn_regex = None
        self.issuer_dn = None


# Adds a "/" after a path for comparison
# This is required to check if a path is indeed a subpath of another path
def _get_slashed_path(path):
    return path if path.endswith("/") else path + "/"


# Gets the location configuration for the most specific path that matches the path
# This is required to ensure that "nested" locations have the same configuration as their parent
def _get_most_specific_location_config(path, locations):
    sorted_paths = sorted(locations.keys())
    sorted_paths.reverse()
    for sorted_path in sorted_paths:
        if _is_subpath_of(path, sorted_path):
            return locations[sorted_path]
    return {}


# Returns if a path is a subpath of others
# others can be a string or collection of strings
def _is_subpath_of(path, others):
    if isinstance(others, str):
        return path == others or path.startswith(_get_slashed_path(others))
    return any(_is_subpath_of(path, p) for p in others)


def _get_locations(locations_env=_get_access_restrictions()):
    # Load access restriction configuration
    # ACCESS_RESTRICTIONS example:
    # {
    #     "/": {'ipfilter': ['10.0.0.0/8'], 'client_cert': true, 'satisfy': 'any'},
    #     "/ws/MyWebService/": {'ipfilter': ['10.0.0.0/8'], 'client_cert': true, 'satisfy': 'all'},
    #     "/CustomRequestHandler/": {'ipfilter': ['10.0.0.0/8']},
    #     "/CustomRequestHandler2/": {'basic_auth': {'user1': 'password', 'user2': 'password2'}},
    # }
    #
    # Note: Default for satisfy is any
    locations = json.loads(locations_env)

    # Add default locations
    for default_path in DEFAULT_LOCATION_PATHS:
        locations[default_path] = _get_most_specific_location_config(
            default_path, locations
        )

    # Get request handlers and determine which request handlers are "dynamic",
    # i.e. most likely for an API, e.g. REST
    dynamic_handler_paths = []
    request_handlers = runtime.get_metadata_value("RequestHandlers")
    paths = [handler["Name"] for handler in request_handlers]
    dynamic_handler_paths = list(
        set(paths) - set(DEFAULT_REQUEST_HANDLER_PATHS)
    )

    # Add dynamic request handler locations
    for dynamic_handler_path in dynamic_handler_paths:
        locations[
            _get_slashed_path(dynamic_handler_path)
        ] = _get_most_specific_location_config(dynamic_handler_path, locations)

    # Get REST request handlers from metadata and add locations
    rest_handler_paths = runtime.get_rest_request_handler_paths()
    for rest_handler_path in rest_handler_paths:
        locations[
            _get_slashed_path(rest_handler_path)
        ] = _get_most_specific_location_config(rest_handler_path, locations)

    # Convert dictionary into list of locations
    index = 0
    result = []

    for path, config in locations.items():
        location = Location()
        location.path = path
        location.index = index

        # Reserved path prefixes are restricted
        if any(path.startswith(prefix) for prefix in RESERVED_PATH_PREFIXES):
            raise Exception(
                "Can not override access restrictions on reserved path [%s]"
                % path
            )

        # Disable proxy buffering for files
        if path == FILE_HANDLER_PATH:
            location.proxy_buffering_enabled = False

        # Enable error interception for default runtime paths
        # This is required for custom error pages
        if (
            _is_subpath_of(path, DEFAULT_REQUEST_HANDLER_PATHS)
            or path in DEFAULT_LOCATION_PATHS
        ):
            location.proxy_intercept_errors_enabled = True

        # Explicitly disable error interception for dynamic request handlers
        # This is not strictly required (default is disabled), but it might be in the future
        if _is_subpath_of(path, dynamic_handler_paths) or _is_subpath_of(
            path, rest_handler_paths
        ):
            location.proxy_intercept_errors_enabled = False

        # Add the  access restrictions configuration
        # "Satisfy" specifies if restrictions should be evaluated as "AND" (all) or "OR" (any)
        if "satisfy" in config:
            if config["satisfy"] in ["any", "all"]:
                location.satisfy = config["satisfy"]
            else:
                raise Exception(
                    "Invalid satisfy value: %s" % config["satisfy"]
                )

        # Add IP filter configuration
        if "ipfilter" in config:
            location.ipfilter_ips = []
            for ip in config["ipfilter"]:
                location.ipfilter_ips.append(ip)

        # Add HTTP basic auth configuration
        if "basic_auth" in config:
            location.basic_auth_enabled = True
            _generate_password_file(config["basic_auth"], str(index))

        # Add client certificate configuration
        if config.get("client-cert") or config.get("client_cert"):
            location.client_cert_enabled = True

        # Add "Issuer DN" check for the client certificate chain. The required header is passed on from an upstream proxy,
        # which in the case of Mendix Cloud is the Front-Facing Fleet
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
