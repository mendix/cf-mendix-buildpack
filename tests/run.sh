#!/bin/bash

set -e

# See more pre-setup scripts in ../.travis.yml

if [[ ! -f run.sh ]]
then
    echo "wrong dir to run tests from."
    exit 1
fi

cf login -a "$CF_ENDPOINT" -u "$CF_USER" -p "$CF_PASSWORD" -o "$CF_ORG" -s "$CF_SPACE" > /dev/null

echo "Begin clean up of environment"
cf apps 2>&1 | grep ops- | awk '{print $1}' | xargs -n 1 -P 5 --no-run-if-empty cf delete -r -f | grep -v 'OK'
cf s 2>&1 | grep ops- | awk '{print $1}' | xargs -n 1 -P 5 --no-run-if-empty cf ds -f $service | grep -v 'OK'
echo "Completed environment clean up"

[ -d "venv" ] && rm -rf "venv"
virtualenv -p python2 venv
. venv/bin/activate >/dev/null
pip install -r requirements.txt -qq

echo 'starting test run'
python venv/bin/nosetests -vv --processes=5 --process-timeout=600 usecase/
