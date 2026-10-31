"""Security layers that apply to every request: sessions, CORS, CSRF,
security headers and rate limiting. Each module explains its own threat."""

from flask import Flask

from app.config import Settings
from app.security.cors import register_cors
from app.security.csrf import register_csrf_protection
from app.security.headers import register_security_headers
from app.security.rate_limit import init_rate_limiting
from app.security.sessions import configure_sessions


def init_security(app: Flask, settings: Settings) -> None:
    configure_sessions(app, settings)
    # Order matters for the before_request hooks: CORS preflights are
    # answered first, then the CSRF check runs, then the rate limiter.
    register_cors(app, settings.cors_allowed_origins)
    register_csrf_protection(app)
    register_security_headers(app)
    init_rate_limiting(app)
