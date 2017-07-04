#!/bin/bash

pids=""
RESULT=0
APPNAME=$1

cf stop $APPNAME
cf delete $APPNAME -r -f
pids="$pids $!"
cf delete-service -f $APPNAME-schnapps 2>&1 &
pids="$pids $!"
cf delete-service -f $APPNAME-database 2>&1 &
pids="$pids $!"
cf delete-service -f $APPNAME-storage 2>&1 &
pids="$pids $!"

for pid in $pids; do
    wait $pid || let "RESULT=1"
done
