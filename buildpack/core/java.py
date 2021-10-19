import json
import logging
import os
import re
import subprocess

import certifi

from buildpack import util

KEYUTIL_JAR = "keyutil-0.4.0.jar"


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
    # While recent versions of AdoptOpenJDK have these on board,
    # we still also have to deal with Oracle JREs / JDKs for now.
    # When we retire support for Mendix 6,
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
    logging.debug("Staging Java finished")


def determine_jdk(java_version, package="jdk"):
    if java_version["vendor"] == "AdoptOpenJDK":
        java_version.update({"type": "AdoptOpenJDK-{}".format(package)})
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
