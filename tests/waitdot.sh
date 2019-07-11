#!/bin/bash

PID=$1
if [ -z "$PID" ]; then
    echo "No pid provided"
    exit 1
fi

echo "Waiting for $PID to end..."
while [ -d /proc/$PID ]; do
    echo -n "."
    sleep 60
done
sleep 5


