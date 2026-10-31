#!/bin/sh
# Container start-up: bring the database schema up to date, then serve the API.
set -e

# Running migrations at start-up is fine for a single instance. With several
# replicas you would run this once as a separate release step, so two
# containers never try to migrate at the same time.
alembic upgrade head

# Ingestion jobs live in memory, so any document still "processing" was
# interrupted by the last shutdown. Mark those failed before serving.
flask --app app recover-ingestion

# One worker process with 8 threads. The rate limiter, the ingestion thread
# pool and the LLM circuit breaker keep their state in process memory, and a
# single process keeps that state consistent. Scaling out would mean moving
# that state into Redis or the database.
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 1 \
    --threads 8 \
    --timeout 120 \
    "app:create_app()"
