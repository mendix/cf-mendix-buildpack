#!/bin/bash

export APP_NAME="sample-mda"

set -e

ls usecase/*.py

if [ -f run.sh ]
then
    echo "correct dir."
else
    echo "wrong dir to run tests from."
    exit 1
fi

if [ -z "${TRAVIS_BRANCH}" ]
then
    export TRAVIS_BRANCH=$(git rev-parse --symbolic-full-name --abbrev-ref HEAD)
fi

cf login -a "$CF_ENDPOINT" -u "$CF_USER" -p "$CF_PASSWORD" -o "$CF_ORG" -s "$CF_SPACE"

# cf login command above exposes the vars if set -x is on top.
set -x

[ -d "venv" ] && rm -rf "venv"
virtualenv -p python2 venv
. venv/bin/activate
pip install -r requirements.txt

bash cleanup.sh

wget -O sample-6.2.0.mda https://s3-eu-west-1.amazonaws.com/mx-ci-binaries/sample-6.2.0.mda
cf push -f manifest.yml --no-start -b https://github.com/mendix/cf-mendix-buildpack.git#$TRAVIS_BRANCH "$APP_NAME"
cf create-service schnapps basic "$APP_NAME"-schnapps
cf create-service PostgreSQL "Basic PostgreSQL Plan" "$APP_NAME"-database
cf create-service amazon-s3 basic "$APP_NAME"-storage
cf bind-service "$APP_NAME" "$APP_NAME"-schnapps
cf bind-service "$APP_NAME" "$APP_NAME"-storage
cf bind-service "$APP_NAME" "$APP_NAME"-database
cf set-env "$APP_NAME" ADMIN_PASSWORD "$MX_PASSWORD"
cf set-env "$APP_NAME" DEBUGGER_PASSWORD "$MX_PASSWORD"
cf start "$APP_NAME"
python venv/bin/nosetests -vv usecase/
cf stop "$APP_NAME"
