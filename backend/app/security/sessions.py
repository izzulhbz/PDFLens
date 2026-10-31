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

Known limitation: because the session lives entirely in the cookie, logging
out clears the cookie in this browser, but a copy stolen earlier would stay
valid until it expires. Server-side sessions would allow revoking it.
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
    # A "permanent" session gets an expiry date and is checked against
    # PERMANENT_SESSION_LIFETIME on every request.
    session.permanent = True
    g.current_user = user


def log_out() -> None:
    session.clear()


def current_user() -> User:
    """The logged-in user. Only call this inside a @login_required view."""
    user: User = g.current_user
    return user


def login_required[**P, R](view: Callable[P, R]) -> Callable[P, R]:
    """Reject the request with 401 unless it carries a valid session for an existing user."""

    @wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        user_id = session.get("user_id")
        user = get_session().get(User, user_id) if isinstance(user_id, int) else None
        if user is None:
            # No session, or the account no longer exists: clear the stale cookie.
            session.clear()
            raise ApiError(401, "unauthorized", "Please log in.")
        g.current_user = user
        return view(*args, **kwargs)

    return wrapper
