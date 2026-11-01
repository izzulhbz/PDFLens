"""Database engine and per-request sessions (SQLAlchemy 2.x).

Each HTTP request gets its own Session, created on first use and closed when
the request ends. Closing a session rolls back anything that wasn't
committed and returns the connection to the pool, so a failed request can
never leave a half-finished transaction behind.
"""

from flask import Flask, current_app, g
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Deterministic constraint and index names. Without this, Postgres invents
# names, and later migrations that drop or alter a constraint have to guess
# what it's called.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def init_db(app: Flask, database_url: str) -> None:
    engine = create_engine(
        database_url,
        # Test each pooled connection before use, so a Postgres restart
        # doesn't surface as errors on the next few requests.
        pool_pre_ping=True,
        # Fail fast instead of hanging when the database is unreachable.
        connect_args={"connect_timeout": 5},
        # SQLAlchemy errors normally include the statement's parameter
        # values, and unexpected errors are logged with their traceback. A
        # failed insert would then write chunk text (the document) or a
        # password hash into the logs. With this, errors show the SQL only.
        hide_parameters=True,
    )
    app.extensions["db_engine"] = engine
    app.extensions["db_sessionmaker"] = sessionmaker(engine, expire_on_commit=False)
    app.teardown_appcontext(_close_session)


def get_session() -> Session:
    """Return the current request's session, creating it on first use."""
    if "db_session" not in g:
        g.db_session = current_app.extensions["db_sessionmaker"]()
    session: Session = g.db_session
    return session


def _close_session(_exc: BaseException | None) -> None:
    session: Session | None = g.pop("db_session", None)
    if session is not None:
        session.close()
