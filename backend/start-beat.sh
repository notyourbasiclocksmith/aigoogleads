#!/bin/bash
set -e

echo "Starting Celery beat scheduler..."
exec celery -A app.jobs.celery_app beat \
    --loglevel=info \
    --schedule=/tmp/celerybeat-schedule
