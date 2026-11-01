"""Logged-in sessions, kept in Flask's signed session cookie.

Flask stores the session in a cookie signed with SECRET_KEY (an HMAC, via
itsdangerous). The browser can read what's inside (only the user ID) but
can't change it without breaking the signature. The signature also contains
a timestamp, so the server itself rejects cookies older than the session
lifetime; it doesn't rely on the browser deleting them.

Cookie flags:
- HttpOnly: JavaScript can't read the cookie, so an XSS bug can't steal it.
- SameSite=Lax: browsers don't send it with cross-site POST, PUT or DELETE
  requests. This is the main CSRF defence (see csrf.py for the second layer).
- Secure: only sent over HTTPS. Turned off only for local plain-HTTP dev.

Revoking sessions: a signed cookie is valid until it expires, wherever it
is, so clearing it in the browser alone wouldn't stop a copy stolen earlier.
The cookie therefore also holds the user's session_version, which must match
the database on every request. Logging out increments it, so every copy of
every session cookie of that user stops working at once: logging out signs
the user out on all devices. (A table of individual sessions would allow
logging out one device only, at the cost of a lookup per session.)
"""

from collections.abc import Callable
from datetime import timedelta
from functools import wraps

from flask import Flask, g, session

from app.config import Settings
from app.db import get_session
from app.errors import ApiError
from app.models import User

SESSION_COOKIE_NAME = "pdflens_session"


def configure_sessions(app: Flask, settings: Settings) -> None:
    app.config.update(
        SESSION_COOKIE_NAME=SESSION_COOKIE_NAME,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.session_cookie_secure,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=settings.session_lifetime_hours),
    )


def log_in(user: User) -> None:
    # Start from an empty session, so nothing set before login carries over.
    session.clear()
    session["user_id"] = user.id
    session["session_version"] = user.session_version
    # A "permanent" session gets an expiry date and is checked against
    # PERMANENT_SESSION_LIFETIME on every request.
    session.permanent = True
    g.current_user = user


def log_out() -> None:
    """End the session here and revoke every other copy of the user's session cookies."""
    user = _session_user()
    if user is not None:
        user.session_version += 1
        get_session().commit()
    session.clear()


def _session_user() -> User | None:
    """The user this request's cookie belongs to, if the cookie is still valid."""
    user_id = session.get("user_id")
    if not isinstance(user_id, int):
        return None
    user = get_session().get(User, user_id)
    if user is None or session.get("session_version") != user.session_version:
        return None
    return user


def current_user() -> User:
    """The logged-in user. Only call this inside a @login_required view."""
    user: User = g.current_user
    return user


def login_required[**P, R](view: Callable[P, R]) -> Callable[P, R]:
    """Reject the request with 401 unless it carries a valid session for an existing user."""

    @wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        user = _session_user()
        if user is None:
            # No session, a revoked one, or the account no longer exists:
            # clear the stale cookie.
            session.clear()
            raise ApiError(401, "unauthorized", "Please log in.")
        g.current_user = user
        return view(*args, **kwargs)

    return wrapper
