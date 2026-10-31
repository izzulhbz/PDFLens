"""Logging set-up and per-request access logs.

Every request gets one log line with metadata only: method, route, status,
duration, request ID, user ID and client IP. Request bodies, query strings,
headers and cookies are never logged, because they can contain passwords,
session cookies or document text.
"""

import logging
import re
import time
import uuid

from flask import Flask, Response, g, request

logger = logging.getLogger("pdflens.request")

# Control characters (including newlines) in a logged value could forge
# extra, fake log lines (log injection, CWE-117), so they are replaced.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def configure_logging(level: str) -> None:
    # basicConfig only adds a handler if none exists yet, so it leaves
    # gunicorn's or pytest's logging set-up alone. The level always applies.
    logging.basicConfig(format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    logging.getLogger().setLevel(level)


def register_request_logging(app: Flask) -> None:
    @app.before_request
    def start_timer() -> None:
        g.request_started = time.perf_counter()
        # Generated server-side, never taken from a client header, so a
        # client can't plant misleading IDs in our logs.
        g.request_id = uuid.uuid4().hex

    @app.after_request
    def log_request(response: Response) -> Response:
        duration_ms = (time.perf_counter() - g.get("request_started", time.perf_counter())) * 1000
        response.headers["X-Request-ID"] = g.get("request_id", "-")
        user = g.get("current_user")
        logger.info(
            "request_id=%s method=%s route=%s status=%s duration_ms=%.1f user_id=%s ip=%s",
            g.get("request_id", "-"),
            request.method,
            _route_for_log(),
            response.status_code,
            duration_ms,
            user.id if user is not None else "-",
            request.remote_addr,
        )
        return response


def _route_for_log() -> str:
    # Log the route pattern (e.g. /api/documents/<int:document_id>) rather
    # than the raw path: it contains no user input and groups well. Requests
    # that match no route fall back to the cleaned-up path.
    if request.url_rule is not None:
        return request.url_rule.rule
    return _CONTROL_CHARS.sub("?", request.path)[:200]
