#!/bin/bash

set -e

ls usecase/*.py

if [ -f run.sh ]
then
    echo "correct dir."
else
    echo "wrong dir to run tests from."
    exit 1
fi

cf login -a "$CF_ENDPOINT" -u "$CF_USER" -p "$CF_PASSWORD" -o "$CF_ORG" -s "$CF_SPACE"

# cf login command above exposes the vars if set -x is on top.
set -x

[ -d "venv" ] && rm -rf "venv"
virtualenv -p python2 venv
. venv/bin/activate
pip install -r requirements.txt

echo "Begin clean up of environment"
cf apps | grep ops- | awk '{print $1}' | xargs -n 1 cf delete -r -f | true
cf s | grep ops- | awk '{print $1}' | xargs -n 1 cf ds -f | true
echo "Completed environment clean up"

python venv/bin/nosetests -vv --processes=3 --process-timeout=600 usecase/
