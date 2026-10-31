"""Health endpoints.

Two endpoints, following the usual liveness/readiness split:
- GET /api/health        "Is the process up?" Cheap, touches nothing else.
                         Docker's healthcheck uses it.
- GET /api/health/ready  "Can it do real work?" Checks Postgres (and the
                         pgvector extension) and Ollama.

Only the status of each dependency is returned, never versions, hostnames or
error messages, because these endpoints need no login.
"""

import logging

import httpx
from flask import Blueprint, Response, current_app, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_session
from app.ollama import has_model, list_models

logger = logging.getLogger(__name__)

bp = Blueprint("health", __name__, url_prefix="/api/health")


@bp.get("")
def liveness() -> Response:
    return jsonify(status="ok")


@bp.get("/ready")
def readiness() -> tuple[Response, int]:
    checks = {"database": _check_database(), "ollama": _check_ollama()}
    # Only the database is essential. Without Ollama, uploads and questions
    # fail, but logging in and listing documents still work, so Ollama
    # being down is reported without marking the whole API unavailable.
    ready = checks["database"] == "ok"
    body = jsonify(status="ok" if ready else "unavailable", checks=checks)
    return body, 200 if ready else 503


def _check_database() -> str:
    try:
        installed = (
            get_session()
            .execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            .scalar()
        )
    except SQLAlchemyError as exc:
        # Log the exception type only: driver messages can include hostnames.
        logger.warning("Database health check failed: %s", type(exc).__name__)
        return "unreachable"
    return "ok" if installed else "pgvector_missing"


def _check_ollama() -> str:
    settings = current_app.extensions["settings"]
    try:
        models = list_models(current_app.extensions["ollama_http"])
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Ollama health check failed: %s", type(exc).__name__)
        return "unreachable"
    if not has_model(settings.ollama_embed_model, models):
        return "embed_model_missing"
    return "ok"
