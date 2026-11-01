"""Rate limiting with Flask-Limiter.

Requests are counted per client IP address in fixed time windows (for
example "5 per minute" allows 5 requests per calendar minute). Counts live
in process memory, which is accurate because gunicorn runs one worker
process (see entrypoint.sh). Several workers or replicas would each keep
their own counts, so they would need shared storage such as Redis
(storage_uri="redis://...").

Login has a second limit per account (email address), counting failed
attempts only, because a botnet spreads its guesses over many IPs and never
trips a per-IP limit. The trade-off: someone who keeps guessing wrong can
lock the real owner out of logging in until the window passes.

Behind Nginx, every request arrives from Nginx's IP address. The app then
reads the real client IP from X-Forwarded-For, which is only trusted when
TRUSTED_PROXY_COUNT says a proxy is there (see create_app).
"""

from collections.abc import Callable

from flask import Flask, Response, current_app, request, session
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


def login_account() -> str:
    """Rate-limit key for logins: the account (email) being tried, or the IP if none."""
    data = request.get_json(silent=True)
    email = data.get("email") if isinstance(data, dict) else None
    if isinstance(email, str) and email.strip():
        # Normalised like the login itself, so "Alice@x.com" and
        # "alice@x.com " count against the same account.
        return f"login:{email.strip().lower()[:320]}"
    return f"ip:{get_remote_address()}"


def failed_login(response: Response) -> bool:
    """Count only failed logins against the per-account limit."""
    return response.status_code == 401


def limit_from_settings(name: str) -> Callable[[], str]:
    """A limit read from Settings on each request, so tests and .env can change it."""
    return lambda: str(getattr(current_app.extensions["settings"], name))
