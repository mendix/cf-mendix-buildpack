#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

SUCCESS = 0

# Starting the Mendix Runtime can fail in both a temporary or permanent way.
# Some of the errors can be fixed with some help of the user.
#
# The default m2ee cli program will only handle a few of these cases, by
# providing additional hints or interactive choices to fix the situation and
# will default to echoing back the error message received from the runtime.

# Database to be used does not exist
start_NO_EXISTING_DB = 2

# Database structure is out of sync with the application domain model, DDL
# commands need to be run to synchronize the database.
start_INVALID_DB_STRUCTURE = 3

# Constant definitions used in the application model are missing from the
# configuration.
start_MISSING_MF_CONSTANT = 4

# In the application database, a user account was detected which has the
# administrative role (as specified in the modeler) and has password '1'.
start_ADMIN_1 = 5

# ...
start_INVALID_STATE = 6
start_MISSING_DTAP = 7
start_MISSING_BASEPATH = 8
start_MISSING_RUNTIMEPATH = 9
start_INVALID_LICENSE = 10
start_SECURITY_DISABLED = 11
start_STARTUP_ACTION_FAILED = 12
start_NO_MOBILE_IN_LICENSE = 13
