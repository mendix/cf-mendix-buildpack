#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3
STATE_DEPENDENT = 4

DUNNO = -1


def check(runner, client):
    (runtime_state, message) = _check_process(runner, client)
    if runtime_state != DUNNO:
        print(message)
        return runtime_state

    (runtime_health, message) = _check_health(client)
    if runtime_health != STATE_OK:
        print(message)
        return runtime_health

    (critical_log_status, message) = _check_critical_logs(client)
    if critical_log_status != STATE_OK:
        print(message)
        return critical_log_status

    # everything seems to be fine, print version info and exit
    about_feedback = client.about().get_feedback()
    print(
        "MxRuntime OK: healthy, using version %s" % about_feedback["version"]
    )
    return STATE_OK


def check_process(runner, client):
    (status, message) = _check_process(runner, client)
    print(message)
    if status is DUNNO:
        return 0
    return status


def check_health(runner, client):
    if client.ping():
        (health_status, health_message) = _check_health(client)
        print(health_message)
        return health_status
    print("Runtime not running. Health could not be determined")
    return STATE_UNKNOWN


def check_critical_logs(runner, client):
    if client.ping():
        (critical_logs_status, critical_logs_message) = _check_critical_logs(
            client
        )
        print(critical_logs_message)
        return critical_logs_status
    print("Runtime not running. Critical Logs could not be determined")
    return STATE_UNKNOWN


def _check_process(runner, client):
    pid = runner.get_pid()

    if pid is None:
        message = "MxRuntime OK: Not running."
        return (STATE_OK, message)
    pid_alive = runner.check_pid()
    m2ee_alive = client.ping()

    if pid_alive and not m2ee_alive:
        message = (
            "MxRuntime CRITICAL: pid %s is alive, but m2ee does not "
            "respond." % runner.get_pid()
        )
        return (STATE_CRITICAL, message)

    if not pid_alive and not m2ee_alive:
        message = (
            "MxRuntime CRITICAL: pid %s is not available, m2ee does "
            "not respond." % runner.get_pid()
        )
        return (STATE_CRITICAL, message)

    if not pid_alive and m2ee_alive:
        message = (
            "MxRuntime WARNING: pid %s is not available, but m2ee "
            "responds." % runner.get_pid()
        )
        return (STATE_WARNING, message)

    if not m2ee_alive:
        message = (
            "MxRuntime WARNING: plugin has broken logic, m2ee should "
            "be alive"
        )
        return (STATE_WARNING, message)

    status_feedback = client.runtime_status().get_feedback()
    if status_feedback["status"] == "starting":
        message = "MxRuntime WARNING: application is still starting up..."
        return (STATE_WARNING, message)
    elif status_feedback["status"] != "running":
        message = (
            "MxRuntime CRITICAL: application is in state %s"
            % status_feedback["status"]
        )
        return (STATE_CRITICAL, message)

    return (DUNNO, "MxRuntime OK")


def _check_health(client):
    health_response = client.check_health()
    if not health_response.has_error():
        feedback = health_response.get_feedback()
        if feedback["health"] == "healthy":
            pass
        elif feedback["health"] == "sick":
            message = "MxRuntime WARNING: Health: %s" % feedback["diagnosis"]
            return (STATE_WARNING, message)
        elif feedback["health"] == "unknown":
            # no health check action was configured
            pass
        else:
            message = (
                "MxRuntime WARNING: Unexpected health check status: %s"
                % feedback["health"]
            )
            return (STATE_WARNING, message)
    else:
        if (
            health_response.get_result() == 3
            and health_response.get_cause() == "java.lang.IllegalArgument"
            "Exception: Action should not be null"
        ):
            # Because of an incomplete implementation, in Mendix 2.5.4 or
            # 2.5.5 this means that the runtime is health-check
            # capable, but no health check microflow is defined.
            pass
        elif (
            health_response.get_result()
            == health_response.ERR_ACTION_NOT_FOUND
        ):
            # Admin action 'check_health' does not exist.
            pass
        else:
            message = (
                "MxRuntime WARNING: Health check failed unexpectedly: "
                "%s" % health_response.get_error()
            )
            return (STATE_WARNING, message)
    return (STATE_OK, "Health check OK")


def _check_critical_logs(client):
    errors = client.get_critical_log_messages()
    if len(errors) != 0:
        message = "\n".join(
            [
                "MxRuntime CRITICAL: %d critical error(s) were "
                "logged" % len(errors)
            ]
            + errors
        )
        return (STATE_CRITICAL, message)
    return (STATE_OK, "No critical log messages")
