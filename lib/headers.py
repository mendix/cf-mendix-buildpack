import json
import os
import re

from m2ee import logger


DEFAULT_HEADERS = {
    "X-Frame-Options": "(?i)(^allow-from https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$|^deny$|^sameorigin$)",  # noqa: E501
    "Referrer-Policy": "(?i)(^no-referrer$|^no-referrer-when-downgrade$|^origin|origin-when-cross-origin$|^same-origin|strict-origin$|^strict-origin-when-cross-origin$|^unsafe-url$)",  # noqa: E501
    "Access-Control-Allow-Origin": "(?i)(^\*$|^null$|^https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$)",  # noqa: E501
    "X-Content-Type-Options": "(?i)(^nosniff$)",
    "Content-Security-Policy": "[a-zA-Z0-9:;/''\"\*_\- \.\n?=%&]+",
    "X-Permitted-Cross-Domain-Policies": "(?i)(^all$|^none$|^master-only$|^by-content-type$|^by-ftp-filename$)",  # noqa: E501
    "X-XSS-Protection": "(?i)(^0$|^1$|^1; mode=block$|^1; report=https?://([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(:\d+)?$)",  # noqa: E501
}


def parse_headers():
    header_config = ""
    headers_from_json = {}

    # this is kept for X-Frame-Options backward compatibility
    x_frame_options = os.environ.get("X_FRAME_OPTIONS", "ALLOW")
    if x_frame_options != "ALLOW":
        headers_from_json["X-Frame-Options"] = x_frame_options

    headers_json = os.environ.get("HTTP_RESPONSE_HEADERS", "{}")

    try:
        headers_from_json.update(json.loads(headers_json))
    except Exception as e:
        logger.error(
            "Failed to parse HTTP_RESPONSE_HEADERS, due to invalid JSON string: '{}'".format(
                headers_json
            ),
            exc_info=True,
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
            logger.debug("Added header {} to nginx config".format(header_key))
        else:
            logger.warning(
                "Skipping {} config, value '{}' is not valid".format(
                    header_key, header_value
                )
            )

    return header_config
