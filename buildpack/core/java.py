import json
import logging
import os
import re
import subprocess

import certifi
from buildpack import util
from lib.m2ee.version import MXVersion
from lib.m2ee.util import strtobool


JAVA_VERSION_OVERRIDE_KEY = "JAVA_VERSION"
DEFAULT_GC_COLLECTOR = "Serial"
SUPPORTED_GC_COLLECTORS = ["Serial", "G1"]


def get_java_major_version(runtime_version):
    result = 8
    if os.getenv(JAVA_VERSION_OVERRIDE_KEY):
        return _get_major_version(os.getenv(JAVA_VERSION_OVERRIDE_KEY))
    if runtime_version >= MXVersion("8.0.0"):
        result = 11
    return _get_major_version(result)


def _get_major_version(version):
    # Java 8
    if isinstance(version, str) and (
        version.startswith("8u") or version.startswith("1.8")
    ):
        return 8
    # Java >= 11
    major_version = int(str(version).split(".", maxsplit=1)[0])
    if major_version >= 8:
        return major_version
    # Java < 8 is not supported
    raise ValueError(f"Cannot determine major version for Java [{version}]")


def _get_security_properties_file(jvm_location, java_major_version):
    conf_dir = ""
    if java_major_version == 8:
        conf_dir = "lib"
    elif java_major_version >= 11:
        conf_dir = "conf"
    else:
        raise ValueError(
            f"Cannot determine security subdirectory for Java [{java_major_version}]"
        )
    return os.path.join(
        os.path.abspath(jvm_location), conf_dir, "security", "java.security"
    )


ENABLE_OUTGOING_TLS_10_11_KEY = "ENABLE_OUTGOING_TLS_10_11"


def _is_outgoing_tls_10_11_enabled():
    return bool(strtobool(os.getenv(ENABLE_OUTGOING_TLS_10_11_KEY, "false")))


# Configures TLSv1.0 and TLSv1.1 for outgoing connections
# These two protocols are considered insecure
# and have been disabled in OpenJDK after March 2021
# Re-enabling them is at your own risk!
def _configure_outgoing_tls_10_11(jvm_location, java_major_version):
    if _is_outgoing_tls_10_11_enabled():
        security_properties_file = ""
        try:
            security_properties_file = _get_security_properties_file(
                jvm_location, java_major_version
            )
        except ValueError as exception:
            logging.error(
                "Not enabling TLSv1.0 and TLSv1.1 for outgoing connections: %s",
                exception,
            )
            return
        if not (
            os.path.exists(security_properties_file)
            and os.access(security_properties_file, os.W_OK)
        ):
            logging.error(
                "Java security properties file does not exist at expected location"
                " or is not writeable, not enabling TLSv1.0 and TLSv1.1"
                " for outgoing connections"
            )
            return
        logging.warning(
            "Enabling TLSv1.0 and TLSv1.1 for outgoing connections. "
            "These protocols are considered insecure and End-Of-Life."
        )
        with open(security_properties_file, "r+") as f:
            lines = f.readlines()
            f.seek(0)
            in_property = False
            for line in lines:
                if line.startswith("jdk.tls.disabledAlgorithms"):
                    in_property = True
                if in_property:
                    line = re.sub(r"TLSv1(\.1)?(\s*\,)?\s*", "", line)
                    # Remove trailing comma
                    if line.rstrip().endswith(r","):
                        line = line.rstrip()[:-1]
                    f.write(line)
                    if not line.endswith("\\\n"):
                        # Disable line modification after property has been parsed
                        # This is required for multi-line properties
                        # with one or more line separators (backslash)
                        in_property = False
                else:
                    f.write(line)
            f.truncate()
    else:
        logging.debug("Not enabling TLSv1.0 and TLSv1.1 for outgoing connections")


def stage(buildpack_path, cache_path, local_path, java_major_version):
    logging.debug("Staging Java...")

    # Download Java
    util.mkdir_p(os.path.join(local_path, "bin"))
    jvm_location = ensure_and_get_jvm(
        java_major_version,
        buildpack_path,
        cache_path,
        local_path,
        package="jre",
    )

    # Create a symlink in .local/bin/java
    os.symlink(
        # Use .. when JDK is in .local because absolute path
        # is different at staging time
        os.path.join(jvm_location.replace(local_path, ".."), "bin", "java"),
        os.path.join(local_path, "bin", "java"),
    )

    # Import Mozilla CA certificates
    # This is done by a third-party tool (keyutil),
    # using the Python certifi certificate bundle
    #
    # Recent versions of Adoptium have these on board,
    # we should reconsider importing these certificates ourselves.
    dependency = util.resolve_dependency(
        "java.keyutil",
        None,
        buildpack_dir=buildpack_path,
        cache_dir=cache_path,
    )
    _update_java_cacert(
        os.path.basename(dependency["artifact"]), cache_path, jvm_location
    )

    # Configure if TLSv1.0 and TLSv1.1 are allowed for outgoing connections
    _configure_outgoing_tls_10_11(jvm_location, java_major_version)

    logging.debug("Staging Java finished")


def _compose_jvm_target_dir(dependency):
    return f"usr/lib/jvm/{dependency['vendor']}-{dependency['type']}-{dependency['version']}-{dependency['vendor']}-x64"  # noqa: C0301


def _get_java_dependency(
    java_major_version, package, buildpack_dir=os.getcwd(), variables=None
):
    if variables is None:
        variables = {}
    return util.get_dependency(
        f"java.{java_major_version}-{package}", variables, buildpack_dir
    )


def ensure_and_get_jvm(
    java_major_version,
    buildpack_dir,
    cache_dir,
    dot_local_location,
    package="jdk",
):
    # Get Java override full version override
    override_version = os.getenv(JAVA_VERSION_OVERRIDE_KEY)
    overrides = {}
    if override_version:
        logging.info("Overriding Java version to [%s]...", override_version)
        if not override_version.isdigit():
            overrides = {
                "version": override_version,
            }

    # Get dependency
    dependency = _get_java_dependency(
        java_major_version, package, buildpack_dir, overrides
    )

    jdk_dir = _compose_jvm_target_dir(dependency)

    rootfs_java_path = f"/{jdk_dir}"
    if not os.path.isdir(rootfs_java_path):
        logging.debug(
            "Downloading and installing Java %s if required...", package.upper()
        )
        util.resolve_dependency(
            dependency,
            os.path.join(dot_local_location, jdk_dir),
            buildpack_dir=buildpack_dir,
            cache_dir=cache_dir,
            unpack_strip_directories=True,
            overrides=overrides,
        )
        logging.debug("Java %s installed", package.upper())
    else:
        logging.debug("Root FS with Java SDK detected, not installing Java")

    return util.get_existing_directory_or_raise(
        [
            "/" + jdk_dir,
            os.path.join(dot_local_location, jdk_dir),
        ],
        "Java not found",
    )


def _update_java_cacert(jar, cache_dir, jvm_location):
    logging.debug("Importing Mozilla CA certificates into JVM keystore...")
    cacerts_file = os.path.join(jvm_location, "lib", "security", "cacerts")
    if not os.path.exists(cacerts_file):
        logging.warning(
            "Cannot locate Java cacerts file %s. "
            "Skipping update of JVM CA certificates.",
            cacerts_file,
        )
        return

    # Parse the Mozilla CA certificate bundle from certifi
    # and import it into the keystore
    keyutil_jar = os.path.abspath(os.path.join(cache_dir, jar))

    # Import the certificate into the keystore
    try:
        subprocess.check_output(
            (
                os.path.join(jvm_location, "bin", "java"),
                "-jar",
                keyutil_jar,
                "--import",
                "--import-pem-file",
                certifi.where(),
                "--force-new-overwrite",
                "--new-keystore",
                cacerts_file,
                "--password",
                "changeit",
            ),
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as ex:
        logging.error("Error importing certificates: %s", ex.output)
        raise ex

    logging.debug("Import of Mozilla certificates finished")


def _set_jvm_locale(m2ee, java_major_version):
    # override locale providers for java8
    if java_major_version == 8:
        util.upsert_javaopts(m2ee, "-Djava.locale.providers=JRE,SPI,CLDR")


def _set_user_provided_java_options(m2ee):
    options = os.environ.get("JAVA_OPTS", None)
    if options:
        try:
            options = json.loads(options)
        except ValueError:
            logging.error(
                "Failed to parse JAVA_OPTS: invalid JSON",
                exc_info=True,
            )
            raise
        util.upsert_javaopts(m2ee, options)


def _set_jvm_memory(m2ee, vcap):
    limit = get_memory_limit(vcap)

    if limit >= 32768:
        heap_size = limit - 4096
    elif limit >= 16384:
        heap_size = limit - 3072
    elif limit >= 8192:
        heap_size = limit - 2048
    elif limit >= 4096:
        heap_size = limit - 1536
    elif limit >= 2048:
        heap_size = limit - 1024
    else:
        heap_size = int(limit / 2)

    heap_size = str(heap_size) + "M"

    env_heap_size = os.environ.get("HEAP_SIZE")
    max_metaspace_size = os.getenv("MAX_METASPACE_SIZE", "256M")

    util.upsert_javaopts(m2ee, f"-XX:MaxMetaspaceSize={max_metaspace_size}")

    if env_heap_size:
        if int(env_heap_size[:-1]) < limit:
            heap_size = env_heap_size
        else:
            logging.warning(
                "The specified heap size [%s] is larger than the maximum memory of the "
                "container ([%s]). Falling back to a heap size of [%s]",
                env_heap_size,
                str(limit) + "M",
                heap_size,
            )

    util.upsert_javaopts(m2ee, f"-Xmx{heap_size}")
    util.upsert_javaopts(m2ee, f"-Xms{heap_size}")

    logging.debug("Java heap size set to %s", heap_size)

    if os.getenv("MALLOC_ARENA_MAX"):
        logging.info("Using provided environment setting for MALLOC_ARENA_MAX")
    else:
        util.upsert_custom_environment_variable(
            m2ee, "MALLOC_ARENA_MAX", str(max(1, limit / 1024) * 2)
        )


def _set_garbage_collector(m2ee, vcap_data):
    limit = get_memory_limit(vcap_data)

    jvm_garbage_collector = DEFAULT_GC_COLLECTOR
    if limit >= 4096:
        # override collector if memory > 4G
        jvm_garbage_collector = "G1"

    env_jvm_garbage_collector = os.getenv("JVM_GARBAGE_COLLECTOR")
    if env_jvm_garbage_collector:
        if env_jvm_garbage_collector in SUPPORTED_GC_COLLECTORS:
            # override from user-provided variable
            jvm_garbage_collector = env_jvm_garbage_collector
        else:
            logging.warning("Unsupported jvm garbage collector found. The specified "
                            "garbage collector [%s] is not supported. JVM garbage "
                            "collector type falling back to default [%s]",
                            env_jvm_garbage_collector, jvm_garbage_collector)

    util.upsert_javaopts(m2ee, f"-XX:+Use{jvm_garbage_collector}GC")

    logging.info("JVM garbage collector is set to [%s]", jvm_garbage_collector)


def get_memory_limit(vcap):
    max_memory = os.environ.get("MEMORY_LIMIT")

    if max_memory:
        match = re.search("([0-9]+)M", max_memory.upper())
        limit = int(match.group(1))
    else:
        limit = int(vcap["limits"]["mem"])
    return limit


def _set_application_name(m2ee, application_name):
    util.upsert_javaopts(m2ee, f"-DapplicationName={application_name}")


def update_config(m2ee, application_name, vcap_data, runtime_version):
    _set_application_name(m2ee, application_name)
    _set_jvm_memory(m2ee, vcap_data)
    _set_garbage_collector(m2ee, vcap_data)
    _set_jvm_locale(m2ee, get_java_major_version(runtime_version))
    _set_user_provided_java_options(m2ee)
