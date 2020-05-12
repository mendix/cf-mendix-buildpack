#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

import os
import shutil
import subprocess
import socket
import http.client
from .log import logger

try:
    import readline

    # allow - in filenames we're completing without messing up completion
    readline.set_completer_delims(
        readline.get_completer_delims().replace("-", "")
    )
except ImportError:
    pass

try:
    import httplib2
except ImportError:
    logger.critical(
        "Failed to import httplib2. This module is needed by "
        "m2ee. Please povide it on the python library path"
    )
    raise


def unpack(config, mda_name):

    mda_file_name = os.path.join(config.get_model_upload_path(), mda_name)
    if not os.path.isfile(mda_file_name):
        logger.error("file %s does not exist" % mda_file_name)
        return False

    logger.debug("Testing archive...")
    cmd = ("unzip", "-tqq", mda_file_name)
    logger.trace("Executing %s" % str(cmd))
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        (stdout, stderr) = proc.communicate()

        if proc.returncode != 0:
            logger.error(
                "An error occured while testing archive " "consistency:"
            )
            logger.error("stdout: %s" % stdout)
            logger.error("stderr: %s" % stderr)
            return False
        else:
            logger.trace("stdout: %s" % stdout)
            logger.trace("stderr: %s" % stderr)
    except OSError as ose:
        import errno

        if ose.errno == errno.ENOENT:
            logger.error(
                "The unzip program could not be found: %s" % ose.strerror
            )
        else:
            logger.error("An error occured while executing unzip: %s" % ose)
        return False

    logger.debug("Removing everything in model/ and web/ locations...")
    # TODO: error handling. removing model/ and web/ itself should not be
    # possible (parent dir is root owned), all errors ignored for now
    app_base = config.get_app_base()
    shutil.rmtree(os.path.join(app_base, "model"), ignore_errors=True)
    shutil.rmtree(os.path.join(app_base, "web"), ignore_errors=True)

    logger.debug("Extracting archive...")
    cmd = ("unzip", "-oq", mda_file_name, "web/*", "model/*", "-d", app_base)
    logger.trace("Executing %s" % str(cmd))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    (stdout, stderr) = proc.communicate()

    if proc.returncode != 0:
        logger.error("An error occured while extracting archive:")
        logger.error("stdout: %s" % stdout)
        logger.error("stderr: %s" % stderr)
        return False
    else:
        logger.trace("stdout: %s" % stdout)
        logger.trace("stderr: %s" % stderr)

    # XXX: reset permissions on web/ model/ to be sure after executing this
    # function
    return True


def fix_mxclientsystem_symlink(config):
    logger.debug("Running fix_mxclientsystem_symlink...")
    mxclient_symlink = os.path.join(
        config.get_public_webroot_path(), "mxclientsystem"
    )
    logger.trace("mxclient_symlink: %s" % mxclient_symlink)
    real_mxclientsystem_path = config.get_real_mxclientsystem_path()
    logger.trace("real_mxclientsystem_path: %s" % real_mxclientsystem_path)
    if os.path.islink(mxclient_symlink):
        current_real_mxclientsystem_path = os.path.realpath(mxclient_symlink)
        if current_real_mxclientsystem_path != real_mxclientsystem_path:
            logger.debug(
                "mxclientsystem symlink exists, but points "
                "to %s" % current_real_mxclientsystem_path
            )
            logger.debug(
                "redirecting symlink to %s" % real_mxclientsystem_path
            )
            os.unlink(mxclient_symlink)
            os.symlink(real_mxclientsystem_path, mxclient_symlink)
    elif not os.path.exists(mxclient_symlink):
        logger.debug(
            "creating mxclientsystem symlink pointing to %s"
            % real_mxclientsystem_path
        )
        try:
            os.symlink(real_mxclientsystem_path, mxclient_symlink)
        except OSError as e:
            logger.error("creating symlink failed: %s" % e)
    else:
        logger.warn(
            "Not touching mxclientsystem symlink: file exists "
            "and is not a symlink"
        )


def run_post_unpack_hook(post_unpack_hook):
    if os.path.isfile(post_unpack_hook):
        if os.access(post_unpack_hook, os.X_OK):
            logger.info("Running post-unpack-hook: %s" % post_unpack_hook)
            retcode = subprocess.call((post_unpack_hook,))
            if retcode != 0:
                logger.error(
                    "The post-unpack-hook returned a "
                    "non-zero exit code: %d" % retcode
                )
        else:
            logger.error(
                "post-unpack-hook script %s is not "
                "executable." % post_unpack_hook
            )
    else:
        logger.error(
            "post-unpack-hook script %s does not exist." % post_unpack_hook
        )


def check_download_runtime_existence(url):
    h = httplib2.Http(timeout=10)
    logger.debug("Checking for existence of %s via HTTP HEAD" % url)
    try:
        (response_headers, response_body) = h.request(url, "HEAD")
        logger.trace("Response headers: %s" % response_headers)
    except (
        httplib2.HttpLib2Error,
        http.client.HTTPException,
        socket.error,
    ) as e:
        logger.error(
            "Checking download url %s failed: %s: %s"
            % (url, e.__class__.__name__, e)
        )
        return False

    if response_headers["status"] == "200":
        logger.debug("Ok, got HTTP 200")
        return True
    if response_headers["status"] == "404":
        logger.error("The location %s cannot be found." % url)
        return False
    logger.error(
        "Checking download url %s failed, HTTP status code %s"
        % (url, response_headers["status"])
    )
    return False


def download_and_unpack_runtime(url, path):
    if not check_download_runtime_existence(url):
        return

    logger.info("Going to download and extract %s to %s" % (url, path))
    p1 = subprocess.Popen(["wget", "-O", "-", url,], stdout=subprocess.PIPE)
    p2 = subprocess.Popen(
        ["tar", "xz", "-C", path,], stdin=p1.stdout, stdout=subprocess.PIPE
    )
    p1.stdout.close()
    stdout, stderr = p2.communicate()
    if p2.returncode == 0:
        logger.info("Successfully downloaded runtime!")
        return True
    else:
        logger.error("Could not download and unpack runtime:")
        logger.error(stderr)
        return False
