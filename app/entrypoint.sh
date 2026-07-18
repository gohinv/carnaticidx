#!/bin/sh
set -eu

echo "Running database migrations..."
flask db upgrade

echo "Starting gunicorn..."
exec gunicorn -c gunicorn.conf.py "app:app"
