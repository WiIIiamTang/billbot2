#!/usr/bin/bash

cd /app
ls -la

echo "Starting Flask"
python3 /app/run.py &

echo "Starting redbot"
sh /app/start-redbot.sh