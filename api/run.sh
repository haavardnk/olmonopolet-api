#!/bin/bash
# Run database migrations
uv run manage.py migrate

# Start qcluster in the background
nohup uv run manage.py qcluster &

# Start Gunicorn server
uv run gunicorn --limit-request-line 8000 --timeout 60 --bind :7000 --workers 5 api.wsgi:application