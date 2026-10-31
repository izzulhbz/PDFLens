"""PDFLens backend: the Flask application factory.

create_app() builds a fresh, fully configured app. Using a factory instead
of a module-level `app` object means tests can build an app with their own
settings and fake dependencies (a mock Ollama client, a fake embedder), and
nothing connects to a database just because a module was imported.

Run it with:
    gunicorn "app:create_app()"   (Docker)
    flask --app app run           (dev mode)
"""

from pathlib import Path

import httpx
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.api import register_blueprints
from app.config import Settings
from app.db import init_db
from app.embeddings.base import Embedder
from app.embeddings.ollama import OllamaEmbedder
from app.errors import register_error_handlers
from app.ingestion.worker import IngestionWorker, register_cli
from app.logging_config import configure_logging, register_request_logging
from app.security import init_security
from app.storage import UploadStore

# Request bodies are capped at 1 MB app-wide; the upload endpoint raises
# its own limit to fit a 20 MB PDF.
MAX_REQUEST_BYTES = 1024 * 1024


def create_app(
    settings: Settings | None = None,
    *,
    ollama_http: httpx.Client | None = None,
    embedder: Embedder | None = None,
    run_ingestion_inline: bool = False,
) -> Flask:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    app.extensions["settings"] = settings
    if settings.trusted_proxy_count:
        # Take the client IP and scheme from X-Forwarded-For/-Proto, trusting
        # exactly as many proxies as configured and no more.
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=settings.trusted_proxy_count, x_proto=settings.trusted_proxy_count
        )

    init_db(app, settings.database_url)

    # Dependencies are built here and stored on the app, so tests can pass in
    # fakes and the rest of the code never constructs its own.
    ollama_http = ollama_http or httpx.Client(
        base_url=settings.ollama_base_url, timeout=settings.ollama_health_timeout_seconds
    )
    embedder = embedder or OllamaEmbedder(
        ollama_http,
        settings.ollama_embed_model,
        timeout_seconds=settings.ollama_embed_timeout_seconds,
    )
    store = UploadStore(Path(settings.upload_dir))
    app.extensions["ollama_http"] = ollama_http
    app.extensions["embedder"] = embedder
    app.extensions["upload_store"] = store
    app.extensions["ingestion"] = IngestionWorker(
        app.extensions["db_sessionmaker"], embedder, store, inline=run_ingestion_inline
    )

    # Registered first, so its timer starts before every other hook runs and
    # its log line records the final response.
    register_request_logging(app)
    init_security(app, settings)
    register_error_handlers(app)
    register_blueprints(app)
    register_cli(app)
    return app
