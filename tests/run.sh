#!/bin/bash

set -e

# See more pre-setup scripts in ../.travis.yml

if [[ ! -f run.sh ]]
then
    echo "wrong dir to run tests from."
    exit 1
fi

cf login -a "$CF_ENDPOINT" -u "$CF_USER" -p "$CF_PASSWORD" -o "$CF_ORG" -s "$CF_SPACE" > /dev/null

function cleanup {
    echo "begin clean up of environment"
    cf apps 2>&1 | grep ops- | awk '{print $1}' | xargs -n 1 -P 5 --no-run-if-empty cf delete -r -f | grep -v 'OK' || true
    cf s 2>&1 | grep ops- | awk '{print $1}' | xargs -n 1 -P 5 --no-run-if-empty cf ds -f $service | grep -v 'OK' || true
    cf delete-orphaned-routes -f 2>&1 | grep -i deleting || true
    echo "completed environment clean up"
}

cleanup

echo 'starting test run, tests will run in parallel and output shown at the end'

export PYTHONPATH=$PWD/..:$PWD/../lib/
nosetests --verbosity=3 --processes=10 --process-timeout=3600 --with-timer --timer-no-color usecase/test_*.py

cleanup
