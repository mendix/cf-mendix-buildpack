#!/bin/bash

pids=""
RESULT=0
APPNAME=$1

cf create-service schnapps-testfree basic-testfree $APPNAME-schnapps -c '{"app_name":"$APPNAME"}' 2>&1 &
pids="$pids $!"
cf create-service rds-testfree shared-psql-testfree $APPNAME-database 2>&1 &
pids="$pids $!"
cf create-service amazon-s3-testfree shared-testfree $APPNAME-storage 2>&1 &
pids="$pids $!"

for pid in $pids; do
    wait $pid || let "RESULT=1"
done

if [ "$RESULT" == "1" ];
    then
       exit 1
fi

pids=""
cf bind-service $APPNAME $APPNAME-schnapps 2>&1 &
pids="$pids $!"
cf bind-service $APPNAME $APPNAME-database 2>&1 &
pids="$pids $!"
cf bind-service $APPNAME $APPNAME-storage 2>&1 &
pids="$pids $!"

for pid in $pids; do
    wait $pid || let "RESULT=1"
done


if [ "$RESULT" == "1" ];
    then
       exit 1
fi
