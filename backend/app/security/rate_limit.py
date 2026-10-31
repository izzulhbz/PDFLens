"""Rate limiting with Flask-Limiter.

Requests are counted per client IP address in fixed time windows (for
example "5 per minute" allows 5 requests per calendar minute). Counts live
in process memory, which is accurate because gunicorn runs one worker
process (see entrypoint.sh). Several workers or replicas would each keep
their own counts, so they would need shared storage such as Redis
(storage_uri="redis://...").

Behind Nginx, every request arrives from Nginx's IP address. The app then
reads the real client IP from X-Forwarded-For, which is only trusted when
TRUSTED_PROXY_COUNT says a proxy is there (see create_app).
"""

from collections.abc import Callable

from flask import Flask, current_app, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    # Adds X-RateLimit-Limit/-Remaining/-Reset, and Retry-After on a 429.
    headers_enabled=True,
)


def init_rate_limiting(app: Flask) -> None:
    limiter.init_app(app)


def user_or_ip() -> str:
    """Rate-limit key for logged-in endpoints: the user if known, otherwise the IP.

    Counting per user means one heavy user can't use up a limit shared with
    everyone behind the same IP. The user ID comes from the signed session
    cookie, so a client can't pretend to be someone else to reset its count.
    """
    user_id = session.get("user_id")
    return f"user:{user_id}" if isinstance(user_id, int) else f"ip:{get_remote_address()}"


def limit_from_settings(name: str) -> Callable[[], str]:
    """A limit read from Settings on each request, so tests and .env can change it."""
    return lambda: str(getattr(current_app.extensions["settings"], name))
