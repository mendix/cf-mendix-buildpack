#!/bin/bash

export APP_NAME="sample-mda"

set -e
set -x

cf login -a $CF_ENDPOINT -u $CF_USER -p $CF_USER_P -o $CF_ORG -s $CF_SPACE

pip install nosetest requests

bash tests/cleanup.sh

cf push -f tests/manifest.yml --no-start $APP_NAME
cf create-service schnapps basic $APP_NAME-schnapps
cf create-service PostgreSQL "Basic PostgreSQL Plan" $APP_NAME-database
cf create-service amazon-s3 basic $APP_NAME-storage
cf bind-service $APP_NAME $APP_NAME-schnapps
cf bind-service $APP_NAME $APP_NAME-storage
cf bind-service $APP_NAME $APP_NAME-database
cf start $APP_NAME
nosetests tests/
cf stop $APP_NAME

