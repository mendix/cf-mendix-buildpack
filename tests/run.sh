#!/bin/bash

set -e

# See more pre-setup scripts in ../.travis.yml

ls usecase/*.py

if [ -f run.sh ]
then
    echo "correct dir."
else
    echo "wrong dir to run tests from."
    exit 1
fi

cf login -a "$CF_ENDPOINT" -u "$CF_USER" -p "$CF_PASSWORD" -o "$CF_ORG" -s "$CF_SPACE" > /dev/null

echo "Begin clean up of environment"
for app in $(cf apps 2>&1 | grep ops- | awk '{print $1}'); do
    cf delete -r -f $app || true
done
for service in $(cf s 2>&1 | grep ops- | awk '{print $1}'); do
    cf ds -f $service || true
done
echo "Completed environment clean up"

# cf login command above exposes the vars if set -x is on top.
set -x

[ -d "venv" ] && rm -rf "venv"
virtualenv -p python2 venv
. venv/bin/activate
pip install -r requirements.txt --quiet

python venv/bin/nosetests -vv --processes=3 --process-timeout=600 usecase/
