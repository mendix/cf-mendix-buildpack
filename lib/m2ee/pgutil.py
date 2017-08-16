#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

import logging
import os
import subprocess
import time
from m2ee.exceptions import M2EEException

logger = logging.getLogger(__name__)


def dumpdb(config, name=None):
    env = os.environ.copy()
    env.update(config.get_pg_environment())

    if name is None:
        name = ("%s_%s.backup"
                % (env['PGDATABASE'], time.strftime("%Y%m%d_%H%M%S"))
                )

    db_dump_file_name = os.path.join(config.get_database_dump_path(), name)

    logger.info("Writing database dump to %s" % db_dump_file_name)
    cmd = (config.get_pg_dump_binary(), "-O", "-x", "-F", "c")
    logger.trace("Executing %s" % str(cmd))
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=open(db_dump_file_name, 'w+'),
                                stderr=subprocess.PIPE)
        (_, stderr) = proc.communicate()

        if stderr != '':
            raise M2EEException("An error occured while creating database dump: %s" %
                                stderr.strip())
    except OSError as e:
        raise M2EEException("Database dump failed, cmd: %s" % cmd, e)


def restoredb(config, dump_name):
    env = os.environ.copy()
    env.update(config.get_pg_environment())

    db_dump_file_name = os.path.join(
        config.get_database_dump_path(), dump_name
    )
    logger.debug("Restoring %s" % db_dump_file_name)
    cmd = (config.get_pg_restore_binary(), "-d", env['PGDATABASE'],
           "-O", "-n", "public", "-x", db_dump_file_name)
    logger.trace("Executing %s" % str(cmd))
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        (stdout, stderr) = proc.communicate()

        if stderr != '':
            raise M2EEException("An error occured while doing database restore: %s " %
                                stderr.strip())
    except OSError as e:
        raise M2EEException("Database restore failed, cmd: %s" % cmd, e)


def emptydb(config):
    env = os.environ.copy()
    env.update(config.get_pg_environment())

    logger.info("Removing all tables...")
    # get list of drop table commands
    cmd1 = (
        config.get_psql_binary(), "-t", "-c",
        "SELECT 'DROP TABLE ' || n.nspname || '.\"' || c.relname || '\" CASCADE;' "
        "FROM pg_catalog.pg_class AS c LEFT JOIN pg_catalog.pg_namespace AS n "
        "ON n.oid = c.relnamespace WHERE relkind = 'r' AND n.nspname NOT IN "
        "('pg_catalog', 'pg_toast') AND pg_catalog.pg_table_is_visible(c.oid)"
    )
    logger.trace("Executing %s, creating pipe for stdout,stderr" % str(cmd1))
    try:
        proc1 = subprocess.Popen(cmd1, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        (stdout1, stderr1) = proc1.communicate()

        if stderr1 != '':
            raise M2EEException("Emptying database (step 1) failed: %s" % stderr1.strip())
    except OSError as e:
        raise M2EEException("Emptying database (step 1) failed, cmd: %s" % cmd1, e)

    stdin2 = stdout1
    cmd2 = (config.get_psql_binary(),)
    logger.trace("Piping stdout,stderr to %s" % str(cmd2))
    try:
        proc2 = subprocess.Popen(cmd2, env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout2, stderr2) = proc2.communicate(stdin2)

        if stderr2 != '':
            raise M2EEException("Emptying database (step 2) failed: %s" % stderr2.strip())
    except OSError as e:
        raise M2EEException("Emptying database (step 2) failed, cmd: %s" % cmd2, e)

    logger.info("Removing all sequences...")
    # get list of drop sequence commands
    cmd3 = (
        config.get_psql_binary(), "-t", "-c",
        "SELECT 'DROP SEQUENCE ' || n.nspname || '.\"' || c.relname || '\" "
        "CASCADE;' FROM pg_catalog.pg_class AS c LEFT JOIN "
        "pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace WHERE "
        "relkind = 'S' AND n.nspname NOT IN ('pg_catalog', 'pg_toast') AND "
        "pg_catalog.pg_table_is_visible(c.oid)"
    )
    logger.trace("Executing %s, creating pipe for stdout,stderr" % str(cmd3))
    try:
        proc3 = subprocess.Popen(cmd3, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        (stdout3, stderr3) = proc3.communicate()

        if stderr3 != '':
            raise M2EEException("Emptying database (step 3) failed: %s" % stderr3.strip())
    except OSError as e:
        raise M2EEException("Emptying database (step 3) failed, cmd: %s" % cmd3, e)

    stdin4 = stdout3
    cmd4 = (config.get_psql_binary(),)
    logger.trace("Piping stdout,stderr to %s" % str(cmd4))
    try:
        proc4 = subprocess.Popen(cmd4, env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout4, stderr4) = proc4.communicate(stdin4)

        if stderr4 != '':
            raise M2EEException("Emptying database (step 4) failed: %s" % stderr4.strip())
    except OSError as e:
        raise M2EEException("Emptying database (step 4) failed, cmd: %s" % cmd4, e)


def psql(config):
    env = os.environ.copy()
    env.update(config.get_pg_environment())
    cmd = (config.get_psql_binary(),)
    logger.trace("Executing %s" % str(cmd))
    try:
        subprocess.call(cmd, env=env)
    except OSError as e:
        raise M2EEException("An error occured while calling psql, cmd: %s" % cmd, e)
