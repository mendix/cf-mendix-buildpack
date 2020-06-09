import json
import logging
import os
import re
import subprocess

from buildpack import util


def compile(buildpack_path, cache_path, local_path, java_version):
    logging.debug("begin download and install java")
    util.mkdir_p(os.path.join(local_path, "bin"))
    jvm_location = ensure_and_get_jvm(
        java_version, cache_path, local_path, package="jre"
    )
    # create a symlink in .local/bin/java
    os.symlink(
        # use .. when jdk is in .local because absolute path
        # is different at staging time
        os.path.join(jvm_location.replace(local_path, ".."), "bin", "java"),
        os.path.join(local_path, "bin", "java"),
    )
    # update cacert file
    update_java_cacert(buildpack_path, jvm_location)
    logging.debug("end download and install java")


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
    java_version, cache_dir, dot_local_location, package="jdk"
):
    logging.debug("Begin download and install java %s" % package)

    jdk = determine_jdk(java_version, package)

    rootfs_java_path = "/{}".format(compose_jvm_target_dir(jdk))
    if not os.path.isdir(rootfs_java_path):
        logging.debug("rootfs without java sdk detected")
        util.download_and_unpack(
            util.get_blobstore_url(_compose_jre_url_path(jdk)),
            os.path.join(dot_local_location, compose_jvm_target_dir(jdk)),
            cache_dir,
        )
    else:
        logging.debug("rootfs with java sdk detected")
    logging.debug("end download and install java %s" % package)

    return util.get_existing_directory_or_raise(
        [
            "/" + compose_jvm_target_dir(jdk),
            os.path.join(dot_local_location, compose_jvm_target_dir(jdk)),
        ],
        "Java not found",
    )


def update_java_cacert(buildpack_dir, jvm_location):
    logging.debug("Applying Mozilla CA certificates update to JVM cacerts...")
    cacerts_file = os.path.join(jvm_location, "lib", "security", "cacerts")
    if not os.path.exists(cacerts_file):
        logging.warning(
            "Cannot locate cacerts file %s. Skipping update of CA certificates.",
            cacerts_file,
        )
        return

    update_cacert_path = os.path.join(buildpack_dir, "vendor", "cacert")
    if not os.path.exists(update_cacert_path):
        logging.warning(
            "Cannot locate cacert lib folder %s. Skipping  update of CA certificates.",
            update_cacert_path,
        )
        return

    cacert_merged = "cacerts.merged"
    env = dict(os.environ)

    try:
        subprocess.check_output(
            (
                os.path.join(jvm_location, "bin", "java"),
                "-jar",
                os.path.join(update_cacert_path, "keyutil-0.4.0.jar"),
                "-i",
                "--new-keystore",
                cacert_merged,
                "--password",
                "changeit",
                "--import-pem-file",
                os.path.join(update_cacert_path, "cacert.pem"),
                "--import-jks-file",
                "{}:changeit".format(cacerts_file),
            ),
            env=env,
            stderr=subprocess.STDOUT,
        )
    except Exception as ex:
        logging.error("Error applying cacert update: {}".format(ex), ex)
        raise ex

    os.rename(cacert_merged, cacerts_file)
    logging.debug("Update of cacerts file finished.")


def _set_jvm_locale(m2ee_section, java_version):
    javaopts = m2ee_section["javaopts"]

    # override locale providers for java8
    if java_version.startswith("8"):
        javaopts.append("-Djava.locale.providers=JRE,SPI,CLDR")


def _set_user_provided_java_options(m2ee_section):
    javaopts = m2ee_section["javaopts"]
    options = os.environ.get("JAVA_OPTS", None)
    if options:
        try:
            options = json.loads(options)
        except Exception as e:
            logging.error(
                "Failed to parse JAVA_OPTS, due to invalid JSON.",
                exc_info=True,
            )
            raise
        javaopts.extend(options)


def _set_jvm_memory(m2ee_section, vcap, java_version):
    max_memory = os.environ.get("MEMORY_LIMIT")

    if max_memory:
        match = re.search("([0-9]+)M", max_memory.upper())
        limit = int(match.group(1))
    else:
        limit = int(vcap["limits"]["mem"])

    if limit >= 8192:
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
                "specified heap size %s is larger than max memory of the "
                "container (%s), falling back to a heap size of %s",
                env_heap_size,
                str(limit) + "M",
                heap_size,
            )
    javaopts = m2ee_section["javaopts"]

    javaopts.append("-Xmx%s" % heap_size)
    javaopts.append("-Xms%s" % heap_size)

    if java_version.startswith("7"):
        javaopts.append("-XX:MaxPermSize=256M")
    else:
        javaopts.append("-XX:MaxMetaspaceSize=256M")

    logging.debug("Java heap size set to %s", heap_size)

    if os.getenv("MALLOC_ARENA_MAX"):
        logging.info("Using provided environment setting for MALLOC_ARENA_MAX")
    else:
        m2ee_section["custom_environment"]["MALLOC_ARENA_MAX"] = str(
            max(1, limit / 1024) * 2
        )


def update_config(m2ee_section, vcap_data, java_version):
    _set_jvm_memory(m2ee_section, vcap_data, java_version)
    _set_jvm_locale(m2ee_section, java_version)
    _set_user_provided_java_options(m2ee_section)
