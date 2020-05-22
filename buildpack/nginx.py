import crypt
import json
import logging
import os
import re
import subprocess

from buildpack import util
from buildpack.runtime_components import security
from lib.m2ee.version import MXVersion

DEFAULT_HEADERS = {
    "X-Frame-Options": r"(?i)(^allow-from https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$|^deny$|^sameorigin$)",  # noqa: E501
    "Referrer-Policy": r"(?i)(^no-referrer$|^no-referrer-when-downgrade$|^origin|origin-when-cross-origin$|^same-origin|strict-origin$|^strict-origin-when-cross-origin$|^unsafe-url$)",  # noqa: E501
    "Access-Control-Allow-Origin": r"(?i)(^\*$|^null$|^https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$)",  # noqa: E501
    "X-Content-Type-Options": r"(?i)(^nosniff$)",
    "Content-Security-Policy": r"[a-zA-Z0-9:;/''\"\*_\- \.\n?=%&]+",
    "X-Permitted-Cross-Domain-Policies": r"(?i)(^all$|^none$|^master-only$|^by-content-type$|^by-ftp-filename$)",  # noqa: E501
    "X-XSS-Protection": r"(?i)(^0$|^1$|^1; mode=block$|^1; report=https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$)",  # noqa: E501
}


def compile(build_path, cache_path):
    util.download_and_unpack(
        util.get_blobstore_url(
            "/mx-buildpack/nginx-1.15.10-linux-x64-cflinuxfs2-6247377a.tgz"
        ),
        build_path,
        cache_dir=cache_path,
    )


def set_up_files(m2ee):
    lines = ""

    if util.use_instadeploy(m2ee.config.get_runtime_version()):
        mxbuild_upstream = "proxy_pass http://mendix_mxbuild"
    else:
        mxbuild_upstream = "return 501"
    with open("nginx/conf/nginx.conf") as fh:
        lines = "".join(fh.readlines())

    samesite_cookie_workaround = get_path_config(
        MXVersion(str(m2ee.config.get_runtime_version())) < MXVersion("8.10")
    )
    http_headers = parse_headers(samesite_cookie_workaround)
    lines = (
        lines.replace("CONFIG", samesite_cookie_workaround,)
        .replace("NGINX_PORT", str(util.get_nginx_port()))
        .replace("RUNTIME_PORT", str(util.get_runtime_port()))
        .replace("ADMIN_PORT", str(util.get_admin_port()))
        .replace("DEPLOY_PORT", str(util.get_deploy_port()))
        .replace("ROOT", os.getcwd())
        .replace("HTTP_HEADERS", http_headers)
        .replace("MXBUILD_UPSTREAM", mxbuild_upstream)
    )
    for line in lines.split("\n"):
        logging.debug(line)
    with open("nginx/conf/nginx.conf", "w") as fh:
        fh.write(lines)

    gen_htpasswd({"MxAdmin": security.get_m2ee_password()})
    gen_htpasswd(
        {"deploy": os.getenv("DEPLOY_PASSWORD")}, file_name_suffix="-mxbuild"
    )


def parse_headers(samesite_cookie_workaround=False):
    header_config = ""
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
            "Failed to parse HTTP_RESPONSE_HEADERS, due to invalid JSON string: '%s'",
            headers_json,
        )
        raise

    for header_key, header_value in headers_from_json.items():
        regEx = DEFAULT_HEADERS[header_key]
        if regEx and re.match(regEx, header_value):
            escaped_value = header_value.replace('"', '\\"').replace(
                "'", "\\'"
            )
            header_config += "add_header {} '{}';\n".format(
                header_key, escaped_value
            )
            logging.debug("Added header {} to nginx config".format(header_key))
        else:
            logging.warning(
                "Skipping {} config, value '{}' is not valid".format(
                    header_key, header_value
                )
            )

    if samesite_cookie_workaround:
        header_value = 'add_header Set-Cookie "mx-cookie-test=allowed; SameSite=None; Secure; Path=/" always;\n'
        escaped_value = header_value.replace('"', '\\"').replace("'", "\\'")
        header_config += escaped_value

    return header_config


def run():
    nginx_process = subprocess.Popen(
        ["nginx/sbin/nginx", "-p", "nginx", "-c", "conf/nginx.conf"]
    )
    return nginx_process


def gen_htpasswd(users_passwords, file_name_suffix=""):
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


def get_path_config(samesite_cookie_workaround=False):
    # Example for ACCESS_RESTRICTIONS
    # {
    #     "/": {'ipfilter': ['10.0.0.0/8'], 'client_cert': true, 'satisfy': 'any'},
    #     "/ws/MyWebService/": {'ipfilter': ['10.0.0.0/8'], 'client_cert': true, 'satisfy': 'all'},
    #     "/CustomRequestHandler/": {'ipfilter': ['10.0.0.0/8']},
    #     "/CustomRequestHandler2/": {'basic_auth': {'user1': 'password', 'user2': 'password2'}},
    # }
    # Default for satisfy is any

    location_template = """
location %s {
    if ($request_uri ~ ^/(.*\.(css|js)|forms/.*|img/.*|pages/.*)\?[0-9]+$) {
        expires 1y;
    }
    proxy_pass http://mendix;
    %s
    proxy_intercept_errors %s;
    satisfy %s;
    %s
    %s
    %s
}
"""
    root_template = """
location %s {
    if ($request_uri ~ ^/(.*\.(css|js)|forms/.*|img/.*|pages/.*)\?[0-9]+$) {
            expires 1y;
    }
    if ($request_uri ~ ^/((index[\w-]*|login)\.html)?$) {
            HTTP_HEADERS
            add_header Cache-Control "no-cache";
    }
    proxy_pass http://mendix;
    %s
}
proxy_intercept_errors %s;
satisfy %s;
%s
%s
%s
"""

    restrictions = json.loads(os.environ.get("ACCESS_RESTRICTIONS", "{}"))
    if "/" not in restrictions:
        restrictions["/"] = {}

    result = ""
    index = 0
    for path, config in restrictions.items():
        if path in ["/_mxadmin/", "/client-cert-check-internal"]:
            raise Exception(
                "Can not override access restrictions on system path %s" % path
            )
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
            proxy_intercept_errors = "on"
        else:
            proxy_intercept_errors = "off"

        satisfy = "any"
        if "satisfy" in config:
            if config["satisfy"] in ["any", "all"]:
                satisfy = config["satisfy"]
            else:
                raise Exception(
                    "invalid satisfy value: %s" % config["satisfy"]
                )

        ipfilter = []
        if "ipfilter" in config:
            for ip in config["ipfilter"]:
                ipfilter.append("allow " + ip + ";")
            ipfilter.append("deny all;")

        basic_auth = []
        if "basic_auth" in config:
            index += 1
            gen_htpasswd(config["basic_auth"], str(index))
            basic_auth = (
                'auth_basic "Restricted";',
                "auth_basic_user_file ROOT/nginx/.htpasswd%s;" % str(index),
            )

        client_cert = ""
        if config.get("client-cert") or config.get("client_cert"):
            client_cert = "auth_request /client-cert-check-internal;"

        # Temporary fix for SameSite enforcement (runtime will set this cookie from 8.10 onwards)
        proxy_cookie_samesite = None
        if samesite_cookie_workaround:
            proxy_cookie_samesite = 'proxy_cookie_path ~(.*) "$1; SameSite=None; Secure; HttpOnly";'

        template = root_template if path == "/" else location_template
        indent = "\n" + " " * (0 if path == "/" else 4)
        result += template % (
            path,
            proxy_cookie_samesite,
            proxy_intercept_errors,
            satisfy,
            indent.join(ipfilter),
            client_cert,
            indent.join(basic_auth),
        )
    return "\n        ".join(result.split("\n"))
