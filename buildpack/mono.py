import glob
import logging
import os
import platform

from buildpack import util
from buildpack.util import NotFoundException


def get_env_with_monolib(mono_dir):
    env = dict(os.environ)

    env["LD_LIBRARY_PATH"] = mono_dir + "/lib"
    env["MONO_STRICT_MS_COMPLIANT"] = "yes"

    if os.path.basename(mono_dir) == "mono-3.10.0":
        env["LC_ALL"] = "C"

    if not os.path.isfile(os.path.join(mono_dir, "lib", "libgdiplus.so")):
        raise Exception("libgdiplus.so not found in dir %s" % mono_dir)
    return env


def _detect_mono_version(mx_version):
    logging.debug(
        "Detecting Mono Runtime using Mendix version: %s", mx_version
    )

    if mx_version >= 8:
        target = "mono-5.20.1.27"
    elif mx_version >= 7:
        target = "mono-4.6.2.16"
    else:
        target = "mono-3.10.0"
    logging.info("Selecting Mono Runtime: %s", target)
    return target


def _get_mono_path(directory, mono_version):
    return util.get_existing_directory_or_raise(
        [
            os.path.join(directory, mono_version),
            "/opt/" + mono_version,
            "/tmp/" + mono_version,
        ],
        "Mono not found",
    )


def _compose_mono_url_path(mono_version):
    distrib_id = platform.linux_distribution()[0].lower()
    if distrib_id != "ubuntu":
        raise Exception(
            "Only Ubuntu is supported at present, requested distribution: {}".format(
                distrib_id
            )
        )
    distrib_codename = platform.linux_distribution()[2].lower()
    if distrib_codename not in ["trusty", "bionic"]:
        raise Exception(
            "Buildpack supports Trusty and Bionic at the moment, requested version: {}".format(
                distrib_codename
            )
        )
    return "/mx-buildpack/mono/{}-mx-{}-{}.tar.gz".format(
        mono_version, distrib_id, distrib_codename
    )


def ensure_and_get_mono(mx_version, cache_dir):
    logging.debug("Ensuring mono for Mendix %s", mx_version)
    mono_version = _detect_mono_version(mx_version)
    fallback_location = "/tmp/opt"

    if (
        mono_version == "mono-3.10.0"
        and platform.linux_distribution()[2].lower() == "bionic"
    ):
        util.download_and_unpack(
            util.get_blobstore_url(_compose_mono_url_path(mono_version)),
            os.path.join(fallback_location, "store"),
            cache_dir,
        )
        mono_subpath = glob.glob("/tmp/opt/store/*-mono-env-3.10.0")
        mono_location = "/tmp/opt/mono-3.10.0"
        os.symlink(mono_subpath[0], mono_location)
        logging.debug(
            "Using {mono_location}".format(mono_location=mono_location)
        )
        logging.warning(
            "The staging phase is likely going to fail when the default "
            + "settings are used. As a workaround, more disk space needs to be "
            + "allocated for the cache. Consult "
            + "https://docs.cloudfoundry.org/devguide/deploy-apps/large-app-deploy.html "
            + "for more information."
        )
        return mono_location
    else:
        try:
            mono_location = _get_mono_path("/tmp/opt", mono_version)
        except NotFoundException:
            logging.debug("Mono not found in default locations")
            util.download_and_unpack(
                util.get_blobstore_url(_compose_mono_url_path(mono_version)),
                os.path.join(fallback_location, mono_version),
                cache_dir,
            )
            mono_location = _get_mono_path(fallback_location, mono_version)
        logging.debug(
            "Using {mono_location}".format(mono_location=mono_location)
        )
        return mono_location
