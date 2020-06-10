#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

import os
import subprocess
import time

from .log import logger


def dumpdb(config, name=None):

    env = os.environ.copy()
    env.update(config.get_pg_environment())

    if name is None:
        name = "%s_%s.backup" % (
            env["PGDATABASE"],
            time.strftime("%Y%m%d_%H%M%S"),
        )

    db_dump_file_name = os.path.join(config.get_database_dump_path(), name)

    logger.info("Writing database dump to %s" % db_dump_file_name)
    cmd = (config.get_pg_dump_binary(), "-O", "-x", "-F", "c")
    logger.trace("Executing %s" % str(cmd))
    proc = subprocess.Popen(cmd, env=env, stdout=open(db_dump_file_name, "w+"))
    proc.communicate()


def restoredb(config, dump_name):

    if not config.allow_destroy_db():
        logger.error(
            "Refusing to do a destructive database operation "
            "because the allow_destroy_db configuration option "
            "is set to false."
        )
        return False

    env = os.environ.copy()
    env.update(config.get_pg_environment())

    db_dump_file_name = os.path.join(
        config.get_database_dump_path(), dump_name
    )
    if not os.path.isfile(db_dump_file_name):
        logger.error("file %s does not exist: " % db_dump_file_name)
        return False

    logger.debug("Restoring %s" % db_dump_file_name)
    cmd = (
        config.get_pg_restore_binary(),
        "-d",
        env["PGDATABASE"],
        "-O",
        "-n",
        "public",
        "-x",
        db_dump_file_name,
    )
    logger.trace("Executing %s" % str(cmd))
    proc = subprocess.Popen(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    (stdout, stderr) = proc.communicate()

    if stderr != "":
        logger.error("An error occured while calling pg_restore: %s " % stderr)
        return False

    return True


def emptydb(config):

    if not config.allow_destroy_db():
        logger.error(
            "Refusing to do a destructive database operation "
            "because the allow_destroy_db configuration option "
            "is set to false."
        )
        return False

    env = os.environ.copy()
    env.update(config.get_pg_environment())

    logger.info("Removing all tables...")
    # get list of drop table commands
    cmd = (
        config.get_psql_binary(),
        "-t",
        "-c",
        "SELECT 'DROP TABLE ' || n.nspname || '.\"' || c.relname || '\" CASCADE;' "
        "FROM pg_catalog.pg_class AS c LEFT JOIN pg_catalog.pg_namespace AS n "
        "ON n.oid = c.relnamespace WHERE relkind = 'r' AND n.nspname NOT IN "
        "('pg_catalog', 'pg_toast') AND pg_catalog.pg_table_is_visible(c.oid)",
    )
    logger.trace("Executing %s, creating pipe for stdout,stderr" % str(cmd))
    proc1 = subprocess.Popen(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    (stdout, stderr) = proc1.communicate()

    if stderr != "":
        logger.error("An error occured while calling psql: %s" % stderr)
        return False

    stdin = stdout
    cmd = (config.get_psql_binary(),)
    logger.trace("Piping stdout,stderr to %s" % str(cmd))
    proc2 = subprocess.Popen(
        cmd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    (stdout, stderr) = proc2.communicate(stdin)

    if stderr != "":
        logger.error("An error occured while calling psql: %s" % stderr)
        return False

    logger.info("Removing all sequences...")
    # get list of drop sequence commands
    cmd = (
        config.get_psql_binary(),
        "-t",
        "-c",
        "SELECT 'DROP SEQUENCE ' || n.nspname || '.\"' || c.relname || '\" "
        "CASCADE;' FROM pg_catalog.pg_class AS c LEFT JOIN "
        "pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace WHERE "
        "relkind = 'S' AND n.nspname NOT IN ('pg_catalog', 'pg_toast') AND "
        "pg_catalog.pg_table_is_visible(c.oid)",
    )
    logger.trace("Executing %s, creating pipe for stdout,stderr" % str(cmd))
    proc1 = subprocess.Popen(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    (stdout, stderr) = proc1.communicate()

    if stderr != "":
        logger.error("An error occured while calling psql: %s" % stderr)
        return False

    stdin = stdout
    cmd = (config.get_psql_binary(),)
    logger.trace("Piping stdout,stderr to %s" % str(cmd))
    proc2 = subprocess.Popen(
        cmd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    (stdout, stderr) = proc2.communicate(stdin)

    if stderr != "":
        logger.error("An error occured while calling psql: %s" % stderr)
        return False

    return True


def psql(config):
    env = os.environ.copy()
    env.update(config.get_pg_environment())
    cmd = (config.get_psql_binary(),)
    logger.trace("Executing %s" % str(cmd))
    subprocess.call(cmd, env=env)
