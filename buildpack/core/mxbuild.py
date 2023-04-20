import codecs
import json
import logging
import os
import shutil
import subprocess
import zipfile

from buildpack import util
from buildpack.core import java, mono, runtime

BUILD_ERRORS_JSON = "/tmp/builderrors.json"


def build_from_source(
    buildpack_path,
    build_path,
    cache_path,
    local_path,
    runtime_version,
    java_version,
):
    logging.info("Building from source...")

    mono_location = mono.ensure_and_get_mono(
        runtime_version, buildpack_path, cache_path
    )
    mono_env = mono.get_env_with_monolib(mono_location)

    mxbuild_location = os.path.join(local_path, "mxbuild")
    runtime.resolve_runtime_dependency(
        buildpack_path,
        build_path,
        cache_path,
        destination=mxbuild_location,
        prefix="mxbuild",
    )

    jdk_location = java.ensure_and_get_jvm(
        java_version, buildpack_path, cache_path, local_path
    )

    util.lazy_remove_file(BUILD_ERRORS_JSON)

    args = [
        os.path.join(mono_location, "bin/mono"),
        "--config",
        os.path.join(mono_location, "etc/mono/config"),
        os.path.join(mxbuild_location, "modeler/mxbuild.exe"),
        "--target=package",
        "--output=/tmp/model.mda",
        f"--java-home={jdk_location}",
        f"--java-exe-path={os.path.join(jdk_location, 'bin/java')}",
    ]

    if runtime_version >= 6.4 or os.environ.get("FORCE_WRITE_BUILD_ERRORS"):
        args.append(f"--write-errors={BUILD_ERRORS_JSON}")
        logging.debug("Will write build errors to %s", BUILD_ERRORS_JSON)

    if os.environ.get("FORCED_MXBUILD_URL"):
        args.append("--loose-version-check")
        logging.warning("Using forced MxBuild version, the model will be converted")

    args.append(util.get_mpr_file_from_dir(build_path))

    try:
        subprocess.check_call(args, env=mono_env)
    except subprocess.CalledProcessError as ex:
        _log_buildstatus_errors(BUILD_ERRORS_JSON)
        raise RuntimeError(ex) from ex

    for file_name in os.listdir(build_path):
        filepath = os.path.join(build_path, file_name)
        if file_name != ".local":
            if os.path.isdir(filepath):
                shutil.rmtree(filepath)
            else:
                os.unlink(filepath)

    with zipfile.ZipFile("/tmp/model.mda") as zip_file:
        zip_file.extractall(build_path)

    try:
        sourcepush = os.path.join(build_path, ".sourcepush")
        with open(sourcepush, "w", encoding="UTF-8") as dsp:
            dsp.write("sourcepush")
    except OSError as ex:
        logging.warning("Could not write source push indicator: %s", str(ex))

    logging.debug("Deleting Mxbuild, Mono and JDK...")
    for path in (mono_location, mxbuild_location, jdk_location):
        shutil.rmtree(path, ignore_errors=False)
        if os.path.exists(path):
            logging.error("%s not deleted", path)

    logging.info("Building from source completed")


def _log_buildstatus_errors(error_file):
    generic_build_failure = {
        "problems": [
            {
                "severity": "Error",
                "message": "Failed to build the model,"
                "please check application logs for details.",
                "locations": [],
            }
        ]
    }
    input_str = ""
    try:
        with codecs.open(error_file, "r", encoding="utf-8-sig") as errorfile:
            input_str = errorfile.read()
            builddata = json.dumps(json.loads(input_str))
    except (IOError, ValueError):
        logging.exception("Could not read MxBuild error file\n%s", input_str)
        builddata = json.dumps(generic_build_failure)
    logging.error("MxBuild returned errors: %s", builddata)
