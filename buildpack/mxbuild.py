import codecs
import json
import logging
import os
import shutil
import subprocess
import zipfile

import requests

from buildpack import java, mono, util
from buildpack.util import NotFoundException


BUILD_ERRORS_JSON = "/tmp/builderrors.json"


def compile(build_path, cache_path, local_path, runtime_version, java_version):
    mono_location = mono.ensure_and_get_mono(runtime_version, cache_path)
    logging.info("Mono available: %s", mono_location)
    mono_env = mono.get_env_with_monolib(mono_location)

    mxbuild_location = os.path.join(local_path, "mxbuild")

    ensure_mxbuild_in_directory(mxbuild_location, runtime_version, cache_path)

    jvm_location = java.ensure_and_get_jvm(
        java_version, cache_path, local_path
    )

    util.lazy_remove_file(BUILD_ERRORS_JSON)

    args = [
        os.path.join(mono_location, "bin/mono"),
        "--config",
        os.path.join(mono_location, "etc/mono/config"),
        os.path.join(mxbuild_location, "modeler/mxbuild.exe"),
        "--target=package",
        "--output=/tmp/model.mda",
        "--java-home=%s" % jvm_location,
        "--java-exe-path=%s" % os.path.join(jvm_location, "bin/java"),
    ]

    if runtime_version >= 6.4 or os.environ.get("FORCE_WRITE_BUILD_ERRORS"):
        args.append("--write-errors=%s" % BUILD_ERRORS_JSON)
        logging.debug("Will write build errors to %s", BUILD_ERRORS_JSON)

    if os.environ.get("FORCED_MXBUILD_URL"):
        args.append("--loose-version-check")
        logging.warning(
            "Using forced mxbuild version, the model will be converted"
        )

    args.append(util.get_mpr_file_from_dir(build_path))

    try:
        logging.debug("subprocess call %s", args)
        subprocess.check_call(args, env=mono_env)
    except subprocess.CalledProcessError as ex:
        buildstatus_callback(BUILD_ERRORS_JSON)
        raise RuntimeError(ex)

    for file_name in os.listdir(build_path):
        filepath = os.path.join(build_path, file_name)
        if file_name != ".local":
            if os.path.isdir(filepath):
                shutil.rmtree(filepath)
            else:
                os.unlink(filepath)

    zf = zipfile.ZipFile("/tmp/model.mda")
    try:
        zf.extractall(build_path)
    finally:
        zf.close()

    try:
        with open(os.path.join(build_path, ".sourcepush"), "w") as dsp:
            dsp.write("sourcepush")
    except OSError as ex:
        logging.warning("Could not write source push indicator: %s", str(ex))


def buildstatus_callback(error_file):
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
        logging.exception("Could not read mxbuild error file\n%s", input_str)
        builddata = json.dumps(generic_build_failure)
    logging.error("MxBuild returned errors: %s", builddata)
    callback_url = os.environ.get("BUILD_STATUS_CALLBACK_URL")
    if callback_url:
        logging.info("Submitting build status")
        put_buildstatus(callback_url, builddata)
        logging.info("Submitted build status")
    else:
        logging.warning(
            "No build status callback url set, "
            "so not going to submit the status"
        )


def put_buildstatus(callback_url, builddata):
    r = requests.put(callback_url, builddata)
    return r.status_code


def start_mxbuild_server(local_path, runtime_version, java_version):
    cache = "/tmp/downloads"  # disable caching here, not in compile step
    mono_location = mono.ensure_and_get_mono(runtime_version, cache)
    mono_env = mono.get_env_with_monolib(mono_location)
    path = os.path.join(os.getcwd(), "runtimes", str(runtime_version))
    if not os.path.isdir(os.path.join(path, "modeler")):
        ensure_mxbuild_in_directory(
            os.path.join(local_path, "mxbuild"), runtime_version, cache
        )
        path = os.path.join(local_path, "mxbuild")

    jvm_location = java.ensure_and_get_jvm(
        java_version, cache, local_path, package="jdk"
    )
    subprocess.Popen(
        [
            os.path.join(mono_location, "bin/mono"),
            "--config",
            os.path.join(mono_location, "etc/mono/config"),
            os.path.join(path, "modeler", "mxbuild.exe"),
            "--serve",
            "--port=6666",
            "--java-home=%s" % jvm_location,
            "--java-exe-path=%s/bin/java" % jvm_location,
        ],
        env=mono_env,
    )


def _checkout_from_git_rootfs(directory, mx_version):
    mendix_runtimes_path = "/usr/local/share/mendix-runtimes.git"
    if not os.path.isdir(mendix_runtimes_path):
        raise NotFoundException()

    env = dict(os.environ)
    env["GIT_WORK_TREE"] = directory

    # checkout the runtime version
    try:
        subprocess.check_call(
            ("git", "checkout", str(mx_version), "-f"),
            cwd=mendix_runtimes_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return
    except Exception:
        try:
            subprocess.check_call(
                (
                    "git",
                    "fetch",
                    "origin",
                    "refs/tags/{0}:refs/tags/{0}".format(str(mx_version)),
                ),
                cwd=mendix_runtimes_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.check_call(
                ("git", "checkout", str(mx_version), "-f"),
                cwd=mendix_runtimes_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logging.debug("found mx version after updating runtimes.git")
            return
        except Exception:
            logging.debug("tried updating git repo, also failed")
    raise NotFoundException(
        "Could not download mxbuild "
        + str(mx_version)
        + " from updated git repo"
    )


def ensure_mxbuild_in_directory(directory, mx_version, cache_dir):
    if os.path.isdir(os.path.join(directory, "modeler")):
        return
    util.mkdir_p(directory)

    url = os.environ.get("FORCED_MXBUILD_URL")
    if url:
        # don"t ever cache with a FORCED_MXBUILD_URL
        util.download_and_unpack(url, directory, cache_dir="/tmp/downloads")
    else:
        try:
            _checkout_from_git_rootfs(directory, mx_version)
        except NotFoundException as e:
            logging.debug(str(e))
            util.download_and_unpack(
                util.get_blobstore_url(
                    "/runtime/mxbuild-%s.tar.gz" % str(mx_version)
                ),
                directory,
                cache_dir=cache_dir,
            )
