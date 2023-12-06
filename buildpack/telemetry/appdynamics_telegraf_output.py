"""The module is used in runtime to convert metrics from telegraf
for appdynamics Machine Agent"""
import json
import logging
import requests
from requests.exceptions import ConnectionError, ConnectTimeout


METRIC_TREE_BASE_NODE = "Custom Metrics|Mx Runtime Statistics"
AGGREGATION_TYPE = "OBSERVATION"
APPDYNAMICS_MACHINE_AGENT_URL = "http://127.0.0.1:8293/api/v1/metrics"

# Timeout for AppDynamics Machine Agent POST request
APPDYNAMICS_MACHINE_AGENT_TIMEOUT = 30

METRIC_TAGS_MAP = {
    "area": "{}",
    "id": "{}",
    "db": "Database '{}'",
    "activity": "{}",
    "microflow": "{}",
}


def _filter_last(payload):
    """
    The function retrieves from the payload the latest version of
    each metric. It is required since the payload probably can
    contain buffered metrics. But Machine Agent HTTP listener payload
    doesn't support any timestamps.

    """
    last_metrics = {}

    for metric in payload:

        metric_name = metric["metricName"]
        last_metric = last_metrics.get(metric_name)

        if last_metric:
            if metric["timestamp"] > last_metric["timestamp"]:
                last_metrics[metric_name] = metric
        else:
            last_metrics[metric_name] = metric

    filtered_metrics = []

    for metric in last_metrics.values():
        del metric["timestamp"]
        filtered_metrics.append(metric)

    return filtered_metrics


def _map_metric_tags(tags):

    mapped_tag_names = []

    for tag_name, template in METRIC_TAGS_MAP.items():
        tag_value = tags.get(tag_name)

        if tag_value:
            mapped_tag_names.append(template.format(tag_value))

    return mapped_tag_names


def _convert_metric(metric):
    """
    The function convert metric json from Telegraf structure
    to AppDynamics Machine Agent compatible one, but with timestamp
    field. Timestamp will be deleted in '_filter_last()'. If the dict
    "fields" has multiple values instead of 'value', multiple separate
    records will be added in the final list.

    Example:

        metric = {
                "fields": {"value": 1},
                "name": "jvm.memory.used",
                "tags": {
                    "host": "dummy.host.com",
                    "area": "heap",
                    "id": "Eden Space",
                },
                "timestamp": 1647939590,
        }

        _convert_metric(metric)

        # Output:
        # [
        #     {
        #     "metricName": "Custom Metrics|[...]|Eden Space",
        #     "aggregatorType": "OBSERVATION",
        #     "value": 1,
        #     "timestamp": 1647939590,
        #     }
        # ]

    """
    fields = metric.get("fields")

    converted = []

    if fields is None:
        logging.error(
            "Converting metrics for AppDynamics Machine Agent: "
            "invalid format of specific metric (telegraf)."
        )
        return

    for value_name in fields.keys():
        value = fields[value_name]
        if value_name == "value":
            metric_name = metric["name"]
        else:
            metric_name = "_".join((metric["name"], value_name))

        metric_path_list = [METRIC_TREE_BASE_NODE, metric_name]

        tags = metric.get("tags")

        # Some metrics have the same names but different tags.
        # So it is necessary to add branches to AppDynamics Metric Browser
        # according to the tags to display all the metrics.
        # For example, the metric 'jvm.memory.used' has tags 'area':'heap'
        # and 'id': 'Eden Space'. The final metric branch in the metric tree
        # will be: 'jvm.memory.used|heap|Eden Space'.
        if tags:
            metric_path_list.extend(_map_metric_tags(tags))

        metric_path = "|".join(metric_path_list)

        conv_metric = {
            "metricName": metric_path,
            "aggregatorType": AGGREGATION_TYPE,
            "value": value,
            "timestamp": metric["timestamp"],
        }

        converted.append(conv_metric)

    return converted


def convert_and_push_payload():
    """
    The function collect metrics json from STDIN (Telegraf 'output.exec')
    and transform it to the structure of the compatible payload for the
    AppDynamics Machine Agent HTTP listener.

    """
    # AppDynamics Docs: https://docs.appdynamics.com/22.2/en/infrastructure-visibility/machine-agent/extensions-and-custom-metrics/machine-agent-http-listener  # noqa: C0301

    metrics_str = input()
    metrics_dict = json.loads(metrics_str)
    metrics_list = metrics_dict.get("metrics")

    if metrics_list is None:
        logging.error(
            "Converting metrics for AppDynamics Machine Agent: "
            "invalid format of metrics json (telegraf)."
        )
        return

    appdynamics_payload = []

    for metric in metrics_list:
        # Convert each metric from Telegraf json structure
        # to the AppDynamics Machine Agent one.
        converted_metrics = _convert_metric(metric)

        if converted_metrics:
            appdynamics_payload.extend(converted_metrics)

    filtered_appd_payload = _filter_last(appdynamics_payload)

    try:
        resp = requests.post(
            APPDYNAMICS_MACHINE_AGENT_URL,
            json=filtered_appd_payload,
            timeout=APPDYNAMICS_MACHINE_AGENT_TIMEOUT,
        )
        logging.info(
            "Request to AppDynamics Machine Agent. Status code: %s.", resp.status_code
        )
    except (ConnectionError, ConnectTimeout) as exc:
        logging.error("AppDynamics Machine Agent is unreachable. Error: %s.", str(exc))


if __name__ == "__main__":

    convert_and_push_payload()
