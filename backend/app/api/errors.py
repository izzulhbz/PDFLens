"""JSON error responses.

Every error leaves the API in the same shape:
    {"error": {"code": "not_found", "message": "..."}}
Unexpected exceptions are logged in full on the server, but the client only
sees a generic message: stack traces reveal file paths, library versions and
sometimes data, which helps an attacker and never helps a user.
"""

import logging

from flask import Flask, Response, jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def error_response(status: int, code: str, message: str) -> tuple[Response, int]:
    return jsonify(error={"code": code, "message": message}), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException) -> tuple[Response, int]:
        status = exc.code or 500
        code = (exc.name or "error").lower().replace(" ", "_")
        return error_response(status, code, exc.description or "")

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception) -> tuple[Response, int]:
        logger.exception("Unhandled exception: %s", type(exc).__name__)
        return error_response(500, "internal_error", "Something went wrong on our side.")
