#!/bin/bash

set -e
set -x

cf delete -r -f $APP_NAME || true
cf delete-route -f -n $APP_NAME $CF_DOMAIN || true
cf delete-service -f $APP_NAME-database || true
cf delete-service -f $APP_NAME-storage || true
cf delete-service -f $APP_NAME-schnapps || true

