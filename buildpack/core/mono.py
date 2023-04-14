import glob
import logging
import os
import distro

from buildpack import util
from buildpack.util import NotFoundException, get_dependency


def get_env_with_monolib(mono_dir):
    env = dict(os.environ)

    env["LD_LIBRARY_PATH"] = mono_dir + "/lib"
    env["MONO_STRICT_MS_COMPLIANT"] = "yes"

    if os.path.basename(mono_dir) == "mono-3.10.0":
        env["LC_ALL"] = "C"

    if not os.path.isfile(os.path.join(mono_dir, "lib", "libgdiplus.so")):
        raise Exception(f"libgdiplus.so not found in dir {mono_dir}")
    return env


def _detect_mono_version(mx_version):
    logging.debug("Detecting Mono Runtime using Mendix version: %s", mx_version)
    if mx_version >= 8:
        target = "5"
    elif mx_version >= 7:
        target = "4"
    else:
        target = "3"
    logging.info("Selecting Mono Runtime: %s", target)
    return target


def _get_mono_path(directory, mono_version):
    return util.get_existing_directory_or_raise(
        [
            os.path.join(directory, f"mono-{mono_version}"),
            f"/opt/mono-{mono_version}",
            f"/tmp/mono-{mono_version}",
        ],
        "Mono not found",
    )


def _compose_mono_dependency_name(mono_version):
    distrib_id = distro.id().lower()
    if distrib_id != "ubuntu":
        raise Exception(
            "Only Ubuntu is supported at present, "
            f"requested distribution: {distrib_id}"
        )
    distrib_codename = distro.codename().lower()
    if distrib_codename not in ["trusty", "bionic", "jammy"]:
        raise Exception(
            "Buildpack supports Trusty, Bionic, and Jammy at the moment, "
            f"requested version: {distrib_codename}"
        )
    return f"mono.{mono_version}-{distrib_codename}"


def ensure_and_get_mono(mx_version, buildpack_dir, cache_dir):
    logging.debug("Ensuring Mono for Mendix %s", mx_version)
    major_version = _detect_mono_version(mx_version)
    dependency_name = _compose_mono_dependency_name(major_version)
    fallback_location = "/tmp/opt"

    if major_version == "3" and distro.codename().lower() == "bionic":
        dependency = util.resolve_dependency(
            dependency_name,
            os.path.join(fallback_location, "store"),
            buildpack_dir=buildpack_dir,
            cache_dir=cache_dir,
            unpack_strip_directories=True,
        )
        version = dependency["version"]
        mono_subpath = glob.glob(f"/tmp/opt/store/*-mono-env-{version}")
        mono_location = f"/tmp/opt/mono-{version}"
        os.symlink(mono_subpath[0], mono_location)
        logging.debug("Mono available: %s", mono_location)
        logging.warning(
            "The staging phase is likely going to fail when the default "
            "settings are used. As a workaround, more disk space needs to be "
            "allocated for the cache. Consult "
            "https://docs.cloudfoundry.org/devguide/deploy-apps/large-app-deploy.html "
            "for more information."
        )
        return mono_location
    else:
        version = get_dependency(dependency_name, buildpack_dir)["version"]
        try:
            mono_location = _get_mono_path("/tmp/opt", version)
        except NotFoundException:
            logging.debug("Mono not found in default locations")
            util.resolve_dependency(
                dependency_name,
                os.path.join(fallback_location, f"mono-{version}"),
                buildpack_dir=buildpack_dir,
                cache_dir=cache_dir,
                unpack_strip_directories=True,
            )
            mono_location = _get_mono_path(fallback_location, version)
        logging.debug("Mono available: %s", mono_location)
        return mono_location
