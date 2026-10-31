"""PDFLens backend: the Flask application factory.

create_app() builds a fresh, fully configured app. Using a factory instead
of a module-level `app` object means tests can build an app with their own
settings and fake dependencies (for example a mock Ollama client), and
nothing connects to a database just because a module was imported.

Run it with:
    gunicorn "app:create_app()"   (Docker)
    flask --app app run           (dev mode)
"""

import httpx
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.api import register_blueprints
from app.config import Settings
from app.db import init_db
from app.errors import register_error_handlers
from app.logging_config import configure_logging, register_request_logging
from app.security import init_security


def create_app(
    settings: Settings | None = None, *, ollama_http: httpx.Client | None = None
) -> Flask:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.secret_key
    app.extensions["settings"] = settings
    app.extensions["ollama_http"] = ollama_http or httpx.Client(
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_health_timeout_seconds,
    )
    if settings.trusted_proxy_count:
        # Take the client IP and scheme from X-Forwarded-For/-Proto, trusting
        # exactly as many proxies as configured and no more.
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=settings.trusted_proxy_count, x_proto=settings.trusted_proxy_count
        )

    init_db(app, settings.database_url)
    # Registered first, so its timer starts before every other hook runs and
    # its log line records the final response.
    register_request_logging(app)
    init_security(app, settings)
    register_error_handlers(app)
    register_blueprints(app)
    return app
