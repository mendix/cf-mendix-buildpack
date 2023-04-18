import json
import logging
import os
import shutil

from buildpack import util
from buildpack.core import runtime

from . import datadog, telegraf, metrics

NAMESPACE = "mx-agent"
DEPENDENCY = f"mendix.{NAMESPACE}"
ROOT_DIR = ".local"


def is_enabled(runtime_version):
    return meets_version_requirements(runtime_version) and (
        telegraf.is_enabled(runtime_version) or datadog.is_enabled()
    )


def meets_version_requirements(runtime_version):
    # The runtime only supports the agent when the runtime version is greater than 7.14
    return runtime_version >= 7.14


def _get_destination_dir(dot_local=ROOT_DIR):
    return os.path.abspath(os.path.join(dot_local, NAMESPACE))


def stage(buildpack_dir, install_dir, cache_dir, runtime_version):
    if is_enabled(runtime_version):
        util.resolve_dependency(
            DEPENDENCY,
            _get_destination_dir(install_dir),
            buildpack_dir=buildpack_dir,
            cache_dir=cache_dir,
            unpack=False,
        )
        shutil.copy(
            os.path.join(
                buildpack_dir,
                "etc",
                "mx-java-agent",
                "DefaultInstrumentationConfig.json",
            ),
            os.path.join(
                _get_destination_dir(install_dir),
                "DefaultInstrumentationConfig.json",
            ),
        )


def update_config(m2ee):
    runtime_version = runtime.get_runtime_version()
    if not meets_version_requirements(runtime_version):
        logging.warning(
            "Not enabling Mendix Java Agent: runtime version must be 7.14 "
            "or up. Application metrics will not be shipped to third-party "
            "monitoring services."
        )
    if is_enabled(runtime_version):
        _enable_mx_java_agent(m2ee)


def _enable_mx_java_agent(m2ee):
    jar = os.path.join(
        _get_destination_dir(),
        os.path.basename(util.get_dependency(DEPENDENCY)["artifact"]),
    )

    logging.debug("Checking if Mendix Java Agent is enabled...")
    if 0 in [v.find(f"-javaagent:{jar}") for v in util.get_javaopts(m2ee)]:
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
    elif "MetricsAgentConfig" in util.get_custom_runtime_settings(m2ee):
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
                    util.get_custom_runtime_setting(m2ee, "MetricsAgentConfig"),
                ),
            )
        )

    # Default config for fallback
    instrumentation_config = os.path.join(
        _get_destination_dir(), "DefaultInstrumentationConfig.json"
    )

    if "METRICS_AGENT_INSTRUMENTATION_CONFIG" in os.environ:
        instrumentation_config = _to_file(
            "METRICS_AGENT_INSTRUMENTATION_CONFIG",
            os.environ.get("METRICS_AGENT_INSTRUMENTATION_CONFIG"),
        )

    mx_agent_args.append(_to_arg("instrumentation_config", instrumentation_config))

    mx_agent_args = list(filter(lambda x: x, mx_agent_args))
    mx_agent_args_str = f'={",".join(mx_agent_args)}' if mx_agent_args else ""

    util.upsert_javaopts(m2ee, f"-javaagent:{jar}{mx_agent_args_str}")

    # If not explicitly set,
    # - default to StatsD (MxVersion < metrics.MXVERSION_MICROMETER)
    # - default to micrometer (MxVersion >= metrics.MXVERSION_MICROMETER)
    # NOTE : Runtime is moving away from statsd type metrics. If we
    # have customers preferring statsd format, they would need to configure
    # StatsD registry for micrometer.
    # https://docs.mendix.com/refguide/metrics
    metrics_type = "statsd"
    if metrics.micrometer_metrics_enabled(runtime.get_runtime_version()):
        metrics_type = "micrometer"
    try:
        util.upsert_custom_runtime_setting(
            m2ee, "com.mendix.metrics.Type", metrics_type
        )
    except ValueError:
        logging.debug(
            "com.mendix.metrics.Type custom runtime setting exists, not setting"
        )


def _to_file(name, json_content):
    try:
        # Ensure that this contains valid JSON
        json.loads(json_content)

        file_name = name.title().replace("_", "") + ".json"
        file_path = os.path.join(_get_destination_dir(), file_name)

        with open(file_path, "w") as file_handler:
            file_handler.write(json_content)

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
