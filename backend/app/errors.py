"""JSON error responses.

Every error leaves the API in the same shape:
    {"error": {"code": "not_found", "message": "..."}}
Code anywhere in a request can `raise ApiError(...)` to return one.

Unexpected exceptions are logged in full on the server, but the client only
sees a generic message: stack traces reveal file paths, library versions and
sometimes data, which helps an attacker and never helps a user.
"""

import logging

from flask import Flask, Response, jsonify
from werkzeug.exceptions import HTTPException

from app.logging_config import log_unexpected_error

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """An error with a status code and a message that is safe to show the client."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_response(status: int, code: str, message: str) -> tuple[Response, int]:
    return jsonify(error={"code": code, "message": message}), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError) -> tuple[Response, int]:
        return error_response(exc.status, exc.code, exc.message)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException) -> tuple[Response, int]:
        status = exc.code or 500
        code = (exc.name or "error").lower().replace(" ", "_")
        response, status = error_response(status, code, exc.description or "")
        # Keep headers the exception carries, such as Allow on a 405 or
        # Retry-After on a 429, but not its HTML Content-Type.
        for name, value in exc.get_headers():
            if name.lower() != "content-type":
                response.headers[name] = value
        return response, status

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception) -> tuple[Response, int]:
        log_unexpected_error(logger, "Unhandled exception: %s", type(exc).__name__)
        return error_response(500, "internal_error", "Something went wrong on our side.")
