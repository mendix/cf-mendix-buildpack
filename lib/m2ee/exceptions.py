# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
# http://www.mendix.com/
#


class M2EEException(Exception):

    ERR_UNKNOWN = 1

    # configuration errors
    ERR_INVALID_OSGI_CONFIG = 2
    ERR_MISSING_CONFIG = 3

    # start/stop errors
    ERR_START_ALREADY_RUNNING = 4
    ERR_JVM_BINARY_NOT_FOUND = 5
    ERR_JVM_FORKEXEC = 6
    ERR_JVM_TIMEOUT = 7
    ERR_JVM_UNKNOWN = 8
    # AppContainer startup errors
    ERR_APPCONTAINER_EXIT_ZERO = 9
    ERR_APPCONTAINER_UNKNOWN_ERROR = 10
    ERR_APPCONTAINER_ADMIN_PORT_IN_USE = 11
    ERR_APPCONTAINER_RUNTIME_PORT_IN_USE = 12
    ERR_APPCONTAINER_INVALID_JDK_VERSION = 13

    ERR_DOWNLOAD_FAILED = 20

    def __init__(self, message, cause=None, errno=1):
        self.message = message
        self.cause = cause
        self.errno = errno

    def __str__(self):
        strlist = [self.message]
        if self.cause is not None:
            strlist.append("caused by: %s" % self.cause)
        strlist.append("errno: %s" % hex(self.errno))
        return ', '.join(strlist)
