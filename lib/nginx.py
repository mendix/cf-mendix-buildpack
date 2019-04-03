import json
import crypt
import os


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


def get_path_config():
    """
    Example for ACCESS_RESTRICTIONS
    {
        "/": {'ipfilter': ['10.0.0.0/8'], 'client_cert': true, 'satisfy': 'any'},
        "/ws/MyWebService/": {'ipfilter': ['10.0.0.0/8'], 'client_cert': true, 'satisfy': 'all'},
        "/CustomRequestHandler/": {'ipfilter': ['10.0.0.0/8']},
        "/CustomRequestHandler2/": {'basic_auth': {'user1': 'password', 'user2': 'password2'}},
    }
    Default for satisfy is any
    """

    location_template = """
location %s {
    if ($request_uri ~ ^/(.*\.(css|js)|forms/.*|img/.*|pages/.*)\?[0-9]+$) {
        expires 1y;
    }
    proxy_pass http://mendix;
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

        template = root_template if path == "/" else location_template
        indent = "\n" + " " * (0 if path == "/" else 4)
        result += template % (
            path,
            proxy_intercept_errors,
            satisfy,
            indent.join(ipfilter),
            client_cert,
            indent.join(basic_auth),
        )
    return "\n        ".join(result.split("\n"))


if __name__ == "__main__":
    print(get_path_config())
