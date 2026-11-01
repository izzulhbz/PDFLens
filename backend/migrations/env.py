"""Alembic environment: how migrations connect to the database.

The URL comes from the DATABASE_URL environment variable (or the repo-root
.env in dev mode). Tests instead pass an open connection through
config.attributes["connection"], so migrations run against the test database.
"""

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import Connection, create_engine

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.db import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# Used by `alembic revision --autogenerate` and by the schema drift test.
target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        run_migrations(connection)
        return

    # Dev mode: the repo-root .env, by explicit path (in Docker there is no
    # such file and this does nothing). Existing environment variables win,
    # so Docker's settings are never overridden.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. See .env.example.")
    engine = create_engine(url)
    with engine.connect() as conn:
        run_migrations(conn)
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) migrations are not supported; run against a database.")
run_migrations_online()
