"""Shared pytest fixtures.

Unit tests (tests/unit) need nothing running. Integration tests
(tests/integration, automatically marked `integration`) need a Postgres with
pgvector, given by TEST_DATABASE_URL: in dev that's the pdflens_test
database in the Compose Postgres, and in CI a GitHub Actions service.

Ollama is never called for real in tests: each app gets an httpx client
whose MockTransport returns canned responses.
"""

import io
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from dotenv import find_dotenv, load_dotenv
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from app import create_app
from app.config import Settings
from app.embeddings.fake import FakeEmbedder

# In dev mode, TEST_DATABASE_URL comes from the repo-root .env.
load_dotenv(find_dotenv(usecwd=True))

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_SECRET_KEY = "test-only-secret-key-that-is-long-enough"
# Unit-test apps point here. Nothing listens on port 1, so if a unit test
# accidentally touched the database it would fail rather than pass silently.
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/nowhere"
EMBED_MODEL_TAG = "nomic-embed-text:latest"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)


# --- Fake Ollama ----------------------------------------------------------------


def fake_ollama(*model_names: str) -> httpx.Client:
    """An Ollama client whose server reports the given models as pulled."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n} for n in model_names]})
        return httpx.Response(404)

    return httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(handler))


def unreachable_ollama() -> httpx.Client:
    """An Ollama client that fails as if the server were down."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(handler))


def make_settings(database_url: str = UNREACHABLE_DATABASE_URL, **overrides: Any) -> Settings:
    # The test client talks plain HTTP, and a Secure cookie would never be
    # sent back over it. One unit test checks the Secure flag explicitly.
    overrides.setdefault("session_cookie_secure", False)
    overrides.setdefault("secret_key", TEST_SECRET_KEY)
    return Settings(database_url=database_url, **overrides)


def api_client(app: Flask) -> FlaskClient:
    """A test client that sends the CSRF header on every request, like our frontend."""
    client = app.test_client()
    client.environ_base["HTTP_X_PDFLENS_CSRF"] = "1"
    return client


# --- Unit-test app (no database) ------------------------------------------------


@pytest.fixture
def unit_app() -> Flask:
    return create_app(make_settings(), ollama_http=fake_ollama(EMBED_MODEL_TAG))


@pytest.fixture
def unit_client(unit_app: Flask) -> FlaskClient:
    return api_client(unit_app)


class _DownSession:
    """Stands in for a SQLAlchemy session whose database is unreachable."""

    def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


@pytest.fixture
def database_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make health checks see a dead database, without waiting on a real
    connection attempt (which takes seconds to time out on Windows)."""
    monkeypatch.setattr("app.api.health.get_session", _DownSession)


# --- Integration: real Postgres --------------------------------------------------


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; integration tests need Postgres.")
    # Safety net: these tests drop and recreate the whole schema, so refuse
    # to run against anything that isn't clearly a test database.
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail(f"TEST_DATABASE_URL must name a database ending in _test, got {database!r}.")
    return url


def alembic_config(connection: Any) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def migrated_engine(test_database_url: str) -> Iterator[Engine]:
    """An engine for the test database, with a fresh schema built by the migrations."""
    engine = create_engine(test_database_url)
    with engine.begin() as conn:
        # Start from nothing, so the migrations are tested from scratch.
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        command.upgrade(alembic_config(conn), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(migrated_engine: Engine) -> Iterator[Engine]:
    yield migrated_engine
    # Empty every table after each test, so tests can't affect each other.
    with migrated_engine.begin() as conn:
        conn.execute(text("TRUNCATE users, documents, chunks, queries RESTART IDENTITY CASCADE"))


def make_integration_app(
    database_url: str,
    upload_dir: Path,
    *,
    embedder: Any = None,
    inline: bool = True,
    **overrides: Any,
) -> Flask:
    """An app on the test database, with the fake embedder and uploads in a temp folder."""
    settings = make_settings(database_url=database_url, upload_dir=str(upload_dir), **overrides)
    return create_app(
        settings,
        ollama_http=fake_ollama(EMBED_MODEL_TAG),
        embedder=embedder or FakeEmbedder(),
        run_ingestion_inline=inline,
    )


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    return tmp_path / "uploads"


@pytest.fixture
def app(db_engine: Engine, test_database_url: str, upload_dir: Path) -> Flask:
    return make_integration_app(test_database_url, upload_dir)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return api_client(app)


TEST_PASSWORD = "correct horse battery staple"


def register(client: FlaskClient, email: str = "alice@example.com") -> int:
    """Create an account (which also logs the client in) and return its user ID."""
    response = client.post("/api/auth/register", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 201, response.get_json()
    user_id: int = response.get_json()["user"]["id"]
    return user_id


def upload(client: FlaskClient, data: bytes, filename: str = "lecture.pdf") -> Any:
    """POST a file to the upload endpoint as multipart/form-data, like a browser form."""
    return client.post(
        "/api/documents",
        data={"file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )
