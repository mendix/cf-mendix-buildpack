import json
import logging
import os

from buildpack import datadog, telegraf, util

NAMESPACE = "mx-agent"
ARTIFACT = "mx-agent-v0.12.0.jar"
ROOT_DIR = ".local"


def is_enabled(runtime_version):
    return meets_version_requirements(runtime_version) and (
        telegraf.is_enabled() or datadog.is_enabled()
    )


def meets_version_requirements(runtime_version):
    # The runtime only supports the agent when the runtime version is greater than 7.14
    return runtime_version >= 7.14


def _get_destination_dir(dot_local=ROOT_DIR):
    return os.path.abspath(os.path.join(dot_local, NAMESPACE))


def stage(install_dir, cache_dir, runtime_version):
    if is_enabled(runtime_version):
        util.download_and_unpack(
            util.get_blobstore_url(
                "/mx-buildpack/{}/{}".format(NAMESPACE, ARTIFACT)
            ),
            _get_destination_dir(install_dir),
            cache_dir=cache_dir,
            unpack=False,
        )


def update_config(m2ee):
    runtime_version = m2ee.config.get_runtime_version()
    if not meets_version_requirements(runtime_version):
        logging.warning(
            "Not enabling Mendix Java Agent: runtime version must be 7.14 or up. "
            "Application metrics will not be shipped to third-party monitoring services."
        )
    if is_enabled(runtime_version):
        _enable_mx_java_agent(m2ee)


def _enable_mx_java_agent(m2ee):
    jar = os.path.join(_get_destination_dir(), ARTIFACT)

    logging.debug("Checking if Mendix Java Agent is enabled...")
    if 0 in [
        v.find("-javaagent:{}".format(jar))
        for v in m2ee.config._conf["m2ee"]["javaopts"]
    ]:
        logging.debug("Mendix Java Agent is already enabled")
        return

    logging.debug("Enabling Mendix Java Agent...")

    mx_agent_args = []

    if "METRICS_AGENT_CONFIG" in os.environ:
        mx_agent_args.append(
            _to_arg(
                "config",
                _to_file(
                    "METRICS_AGENT_CONFIG",
                    os.environ.get("METRICS_AGENT_CONFIG"),
                ),
            )
        )
    elif "MetricsAgentConfig" in m2ee.config._conf["mxruntime"]:
        logging.warning(
            "Passing MetricsAgentConfig with custom runtime "
            "settings is deprecated. "
            "Please use the METRICS_AGENT_CONFIG environment variable."
        )
        mx_agent_args.append(
            _to_arg(
                "config",
                _to_file(
                    "METRICS_AGENT_CONFIG",
                    m2ee.config._conf["mxruntime"]["MetricsAgentConfig"],
                ),
            )
        )

    if "METRICS_AGENT_INSTRUMENTATION_CONFIG" in os.environ:
        mx_agent_args.append(
            _to_arg(
                "instrumentation_config",
                _to_file(
                    "METRICS_AGENT_INSTRUMENTATION_CONFIG",
                    os.environ.get("METRICS_AGENT_INSTRUMENTATION_CONFIG"),
                ),
            )
        )

    mx_agent_args = list(filter(lambda x: x, mx_agent_args))

    if mx_agent_args:
        mx_agent_args_str = ",".join(mx_agent_args)
    else:
        mx_agent_args_str = ""

    m2ee.config._conf["m2ee"]["javaopts"].extend(
        ["-javaagent:{}={}".format(jar, mx_agent_args_str)]
    )

    # If not explicitly set, default to StatsD
    m2ee.config._conf["mxruntime"].setdefault(
        "com.mendix.metrics.Type", "statsd"
    )


def _to_file(name, json_content):
    try:
        # Ensure that this contains valid JSON
        json.loads(json_content)

        file_name = name.title().replace("_", "") + ".json"
        file_path = os.path.join(_get_destination_dir(), file_name)

        with open(file_path, "w") as fh:
            fh.write(json_content)

        return file_path
    except ValueError:
        logging.error(
            "Error parsing JSON from %s",
            name,
            exc_info=True,
        )
        return None


def _to_arg(key, value):
    if key and value:
        return key + "=" + value
    return None
