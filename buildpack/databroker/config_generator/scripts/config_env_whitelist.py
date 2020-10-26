# This is list of allowed ENV VARS that will be converted into configuration
from buildpack.databroker.config_generator.scripts.constants import (
    ENV_VAR_BROKER_PREFIX,
    NODE_COUNT_KEY,
)

whitelist = [
    "MXRUNTIME_DatabaseType",
    "MXRUNTIME_DatabaseHost",
    "MXRUNTIME_DatabaseName",
    "MXRUNTIME_DatabaseUserName",
    "MXRUNTIME_DatabasePassword",
    ENV_VAR_BROKER_PREFIX + NODE_COUNT_KEY,
]
