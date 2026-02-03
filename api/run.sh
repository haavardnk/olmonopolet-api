#!/bin/bash
# Run database migrations
uv run manage.py migrate

# Start qcluster in the background
uv run manage.py qcluster &

# Start Gunicorn server (foreground for docker logs)
uv run gunicorn --limit-request-line 8000 --timeout 60 --bind :7000 --workers 5 --capture-output --access-logfile - --error-logfile - api.wsgi:application