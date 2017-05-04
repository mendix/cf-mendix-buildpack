#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

import datetime
import logging
import time
from m2ee.client import M2EEAdminException, M2EEAdminNotAvailable

logger = logging.getLogger(__name__)

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3
STATE_DEPENDENT = 4


def check(runner, client):
    process_state, process_message = check_process(runner, client)
    logger.trace("check_process: %s, %s" % (process_state, process_message))

    state = process_state
    message = process_message

    health_state, health_message = check_health(client)
    logger.trace("check_health: %s, %s" % (health_state, health_message))

    if health_state in (STATE_WARNING, STATE_CRITICAL):
        message = "%s; %s" % (message, health_message)
        if state != STATE_CRITICAL:
            state = health_state

    critical_log_state, critical_log_message, loglines = check_critical_logs(client)
    logger.trace("check_critical_logs: %s, %s" % (critical_log_state, critical_log_message))

    if critical_log_state in (STATE_WARNING, STATE_CRITICAL):
        message = "%s; %s" % (message, critical_log_message)
        if state != STATE_CRITICAL:
            state = critical_log_state

    license_state, license_message = check_license(client)
    logger.trace("check_license: %s, %s" % (license_state, license_message))

    if license_state in (STATE_WARNING, STATE_CRITICAL):
        message = "%s; %s" % (message, license_message)
        if state != STATE_CRITICAL:
            state = license_state

    print message
    if loglines is not None:
        print '\n'.join(loglines)
    return state


def check_process(runner, client):
    pid = runner.get_pid()
    pid_alive = runner.check_pid()
    m2ee_alive = client.ping()

    if m2ee_alive is False:
        if pid is None:
            return STATE_OK, "Application is not running."
        elif pid_alive is True:
            return STATE_CRITICAL, \
                "Application process is running, but Admin API is not available."
        elif pid_alive is False:
            return STATE_CRITICAL, \
                "Application should be running, but the application process has disappeared!"
        else:
            return STATE_CRITICAL, "Plugin code has broken logic!"

    pid_message = ""
    if pid is None:
        pid_message = "Pidfile is missing or corrupt"
    elif pid_alive is False:
        pid_message = "Process with pid %s cannot receive signals" % runner.get_pid()

    try:
        version_message = "Using Runtime %s" % client.about()['version']
    except (M2EEAdminException, M2EEAdminNotAvailable) as e:
        version_message = ""

    state = STATE_OK
    m2ee_message = "Application is running"
    try:
        runtime_status = client.runtime_status()['status']
        if runtime_status == 'starting':
            state = STATE_WARNING
            m2ee_message = "Application is still starting up..."
        elif runtime_status != 'running':
            state = STATE_CRITICAL
            m2ee_message = "Application is in state %s" % runtime_status
    except (M2EEAdminException, M2EEAdminNotAvailable) as e:
        state = STATE_CRITICAL
        m2ee_message = str(e)

    message = '; '.join([x for x in [m2ee_message, version_message, pid_message]
                        if x != ""])
    if state == STATE_OK and pid_message != "":
        state = STATE_WARNING

    return (state, message)


def check_health(client):
    try:
        feedback = client.check_health()
        if feedback['health'] == 'healthy':
            return STATE_OK, "Healty"
        elif feedback['health'] == 'sick':
            message = "Health: %s" % feedback['diagnosis']
            return STATE_WARNING, message
        elif feedback['health'] == 'unknown':
            return STATE_UNKNOWN, "Health check not available, health could not be determined"
        else:
            return STATE_WARNING, "Unexpected health check status: %s" % feedback['health']
    except M2EEAdminException as e:
        if e.result == e.ERR_ACTION_NOT_FOUND:
            return STATE_UNKNOWN, "Health check not available, health could not be determined"
        else:
            return STATE_CRITICAL, "Health check failed unexpectedly: %s" % e
    except M2EEAdminNotAvailable as e:
        return STATE_UNKNOWN, "Admin API not available, health could not be determined"


def check_critical_logs(client):
    try:
        errors = client.get_critical_log_messages()
        if len(errors) != 0:
            return STATE_CRITICAL, "%d critical error(s) were logged" % len(errors), errors
        return STATE_OK, "No critical log messages", None
    except M2EEAdminException as e:
        return STATE_CRITICAL, "Checking critical log messages failed unexpectedly: %s" % e, None
    except M2EEAdminNotAvailable as e:
        return STATE_UNKNOWN, \
            "Admin API not available, critical log messages could not be checked", None


def check_license(client):
    try:
        feedback = client.get_license_information()
        if 'license' not in feedback:
            return STATE_OK, "No license activated"
        expiry = feedback['license'].get('ExpirationDate', None)
        if expiry is None:
            return STATE_OK, "License has no expiry date"
        expiry = expiry / 1000
        now = time.time()
        expires_in_days = int((expiry - now) / 86400) + 1
        if expires_in_days == 1:
            expires_in_days_txt = "within a day"
        else:
            expires_in_days_txt = "within %s days" % expires_in_days
        warning = 30 * 86400
        critical = 7 * 86400
        expiry_txt = ("License expires at %s" %
                      datetime.datetime.fromtimestamp(expiry)
                      .strftime("%a, %d %b %Y %H:%M:%S %z")
                      .rstrip())
        if now + critical > expiry:
            return STATE_CRITICAL, "%s (%s)" % (expiry_txt, expires_in_days_txt)
        elif now + warning > expiry:
            return STATE_WARNING, "%s (%s)" % (expiry_txt, expires_in_days_txt)
        else:
            return STATE_OK, expiry_txt
    except M2EEAdminException as e:
        if e.result == M2EEAdminException.ERR_ACTION_NOT_FOUND:
            return STATE_UNKNOWN, "No license info available"
        else:
            return STATE_CRITICAL, "Checking license expiration failed unexpectedly: %s" % e
    except M2EEAdminNotAvailable as e:
        return STATE_UNKNOWN, "Admin API not available, license expiration could not be checked"
