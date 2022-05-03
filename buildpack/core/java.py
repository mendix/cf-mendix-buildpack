import json
import logging
import os
import re
import subprocess
from distutils.util import strtobool

import certifi
from buildpack import util

KEYUTIL_JAR = "keyutil-0.4.0.jar"


def _get_major_version(java_version):
    version = java_version["version"]
    # Java 8
    if version.startswith("8u") or version.startswith("1.8"):
        return 8
    # Java >= 11
    major_version = int(version.split(".")[0])
    if major_version >= 8:
        return major_version
    # Java < 8 is not supported
    raise ValueError("Cannot determine major version for Java [%s]" % version)


def _get_security_properties_file(jvm_location, java_version):
    major_version = _get_major_version(java_version)
    conf_dir = ""
    if major_version == 8:
        conf_dir = "lib"
    elif major_version >= 11:
        conf_dir = "conf"
    else:
        raise ValueError(
            "Cannot determine security subdirectory for Java [%s]"
            % major_version
        )
    return os.path.join(
        os.path.abspath(jvm_location), conf_dir, "security", "java.security"
    )


ENABLE_OUTGOING_TLS_10_11_KEY = "ENABLE_OUTGOING_TLS_10_11"


def _is_outgoing_tls_10_11_enabled():
    return bool(strtobool(os.getenv(ENABLE_OUTGOING_TLS_10_11_KEY, "false")))


# Configures TLSv1.0 and TLSv1.1 for outgoing connections
# These two protocols are considered insecure and have been disabled in OpenJDK after March 2021
# Re-enabling them is at your own risk!
def _configure_outgoing_tls_10_11(jvm_location, java_version):
    if _is_outgoing_tls_10_11_enabled():
        security_properties_file = ""
        try:
            security_properties_file = _get_security_properties_file(
                jvm_location, java_version
            )
        except ValueError as e:
            logging.error(
                "Not enabling TLSv1.0 and TLSv1.1 for outgoing connections: "
                % e
            )
            return
        if not (
            os.path.exists(security_properties_file)
            and os.access(security_properties_file, os.W_OK)
        ):
            logging.error(
                "Java security properties file does not exist at expected location or is not writeable, not enabling TLSv1.0 and TLSv1.1 for outgoing connections"
            )
            return
        logging.warning(
            "Enabling TLSv1.0 and TLSv1.1 for outgoing connections. These protocols are considered insecure and End-Of-Life."
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
                        # This is required for multi-line properties with one or more line separators (backslash)
                        in_property = False
                else:
                    f.write(line)
            f.truncate()
    else:
        logging.debug(
            "Not enabling TLSv1.0 and TLSv1.1 for outgoing connections"
        )


def stage(buildpack_path, cache_path, local_path, java_version):
    logging.debug("Staging Java...")

    # Download Java
    util.mkdir_p(os.path.join(local_path, "bin"))
    jvm_location = ensure_and_get_jvm(
        java_version, buildpack_path, cache_path, local_path, package="jre"
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
    util.resolve_dependency(
        util.get_blobstore_url(
            "/mx-buildpack/java-keyutil/{}".format(KEYUTIL_JAR)
        ),
        None,
        buildpack_dir=buildpack_path,
        cache_dir=cache_path,
    )
    _update_java_cacert(cache_path, jvm_location)

    # Configure if TLSv1.0 and TLSv1.1 are allowed for outgoing connections
    _configure_outgoing_tls_10_11(jvm_location, java_version)

    logging.debug("Staging Java finished")


def determine_jdk(java_version, package="jdk"):
    if java_version["vendor"] == "Adoptium":
        java_version.update({"type": "Adoptium-{}".format(package)})
    else:
        java_version.update({"type": package})

    return java_version


def compose_jvm_target_dir(jdk):
    return "usr/lib/jvm/{type}-{version}-{vendor}-x64".format(
        type=jdk["type"], version=jdk["version"], vendor=jdk["vendor"]
    )


def _compose_jre_url_path(jdk):
    return "/mx-buildpack/{type}-{version}-linux-x64.tar.gz".format(
        type=jdk["type"], version=jdk["version"]
    )


def ensure_and_get_jvm(
    java_version, buildpack_dir, cache_dir, dot_local_location, package="jdk"
):

    jdk = determine_jdk(java_version, package)
    jdk_dir = compose_jvm_target_dir(jdk)

    rootfs_java_path = "/{}".format(jdk_dir)
    if not os.path.isdir(rootfs_java_path):
        logging.debug(
            "Downloading and installing Java {} if required...".format(
                package.upper()
            )
        )
        util.resolve_dependency(
            util.get_blobstore_url(_compose_jre_url_path(jdk)),
            os.path.join(dot_local_location, jdk_dir),
            buildpack_dir=buildpack_dir,
            cache_dir=cache_dir,
            unpack_strip_directories=True,
        )
        logging.debug("Java {} installed".format(package.upper()))
    else:
        logging.debug("Root FS with Java SDK detected, not installing Java")

    return util.get_existing_directory_or_raise(
        [
            "/" + compose_jvm_target_dir(jdk),
            os.path.join(dot_local_location, jdk_dir),
        ],
        "Java not found",
    )


def _update_java_cacert(cache_dir, jvm_location):
    logging.debug("Importing Mozilla CA certificates into JVM keystore...")
    cacerts_file = os.path.join(jvm_location, "lib", "security", "cacerts")
    if not os.path.exists(cacerts_file):
        logging.warning(
            "Cannot locate Java cacerts file %s. Skipping update of JVM CA certificates.",
            cacerts_file,
        )
        return

    # Parse the Mozilla CA certificate bundle from certifi and import it into the keystore
    keyutil_jar = os.path.abspath(os.path.join(cache_dir, KEYUTIL_JAR))

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
        logging.error("Error importing certificates: {}".format(ex.output))
        raise ex

    logging.debug("Import of Mozilla certificates finished")


def _set_jvm_locale(m2ee, java_version):
    # override locale providers for java8
    if java_version.startswith("8"):
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


def _set_jvm_memory(m2ee, vcap, java_version):
    max_memory = os.environ.get("MEMORY_LIMIT")

    if max_memory:
        match = re.search("([0-9]+)M", max_memory.upper())
        limit = int(match.group(1))
    else:
        limit = int(vcap["limits"]["mem"])

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
    if env_heap_size:
        if int(env_heap_size[:-1]) < limit:
            heap_size = env_heap_size
        else:
            logging.warning(
                "The specified heap size [{}] is larger than the maximum memory of the "
                "container ([{}]). Falling back to a heap size of [{}]".format(
                    env_heap_size, str(limit) + "M", heap_size
                )
            )

    util.upsert_javaopts(m2ee, "-Xmx%s" % heap_size)
    util.upsert_javaopts(m2ee, "-Xms%s" % heap_size)

    if java_version.startswith("7"):
        util.upsert_javaopts(m2ee, "-XX:MaxPermSize=256M")
    else:
        util.upsert_javaopts(m2ee, "-XX:MaxMetaspaceSize=256M")

    logging.debug("Java heap size set to %s", heap_size)

    if os.getenv("MALLOC_ARENA_MAX"):
        logging.info("Using provided environment setting for MALLOC_ARENA_MAX")
    else:
        util.upsert_custom_environment_variable(
            m2ee, "MALLOC_ARENA_MAX", str(max(1, limit / 1024) * 2)
        )


def update_config(m2ee, vcap_data, java_version):
    _set_jvm_memory(m2ee, vcap_data, java_version)
    _set_jvm_locale(m2ee, java_version)
    _set_user_provided_java_options(m2ee)
