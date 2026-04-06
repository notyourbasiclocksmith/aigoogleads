#!/bin/bash
set -e

echo "Starting Celery worker..."
exec celery -A app.jobs.celery_app worker \
    --loglevel=info \
    --concurrency=${CELERY_CONCURRENCY:-2} \
    --max-tasks-per-child=50 \
    -Q default,optimization,pipeline
