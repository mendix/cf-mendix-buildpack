#!/bin/bash


ls usecase/*.py

if [ -f run.sh ]
then
    echo "correct dir."
else
    echo "wrong dir to run tests from."
    exit 1
fi

cf login -a "$CF_ENDPOINT" -u "$CF_USER" -p "$CF_PASSWORD" -o "$CF_ORG" -s "$CF_SPACE" || exit 1

echo "Begin clean up of environment"
cf apps | grep ops- | awk '{print $1}' | xargs -n 1 cf delete -r -f
cf s | grep ops- | awk '{print $1}' | xargs -n 1 cf ds -f
echo "Completed environment clean up"

# cf login command above exposes the vars if set -x is on top.
set -e
set -x

[ -d "venv" ] && rm -rf "venv"
virtualenv -p python2 venv
. venv/bin/activate
pip install -r requirements.txt

python venv/bin/nosetests -vv --processes=3 --process-timeout=600 usecase/
