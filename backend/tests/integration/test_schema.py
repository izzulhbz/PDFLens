"""The migrated schema: pgvector, the vector column, indexes, and model/migration drift."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, inspect, text

from app.db import Base
from app.models import EMBEDDING_DIM
from tests.conftest import alembic_config


def test_pgvector_extension_is_installed(db_engine):
    with db_engine.connect() as conn:
        version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar()

    assert version is not None


def test_embedding_column_has_the_model_dimension(db_engine):
    with db_engine.connect() as conn:
        column_type = conn.execute(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
            )
        ).scalar()

    assert column_type == f"vector({EMBEDDING_DIM})"


def test_embedding_index_is_hnsw_with_cosine_ops(db_engine):
    with db_engine.connect() as conn:
        index_sql = conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_chunks_embedding_hnsw'")
        ).scalar()

    assert index_sql is not None
    assert "USING hnsw (embedding vector_cosine_ops)" in index_sql


def test_chunks_have_an_index_led_by_document_id(db_engine):
    indexes = inspect(db_engine).get_indexes("chunks")
    unique_constraints = inspect(db_engine).get_unique_constraints("chunks")

    leading_columns = [ix["column_names"][0] for ix in indexes] + [
        uq["column_names"][0] for uq in unique_constraints
    ]
    assert "document_id" in leading_columns


def test_models_match_migrations(db_engine):
    # If someone edits app/models.py without writing a migration (or the
    # other way round), this lists the differences and fails.
    with db_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    assert diff == []


def test_check_constraints_have_the_names_the_models_give_them(db_engine):
    # compare_metadata above ignores CHECK constraints, which is how every
    # one of them once ended up named ck_<table>_ck_<table>_<name> by the
    # migrations. Error messages and future migrations rely on these names.
    expected = {
        (table.name, str(constraint.name))
        for table in Base.metadata.sorted_tables
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    inspector = inspect(db_engine)

    actual = {
        (table, check["name"])
        for table in inspector.get_table_names()
        if table != "alembic_version"
        for check in inspector.get_check_constraints(table)
    }

    assert actual == expected


def test_migrations_downgrade_and_upgrade_cleanly(db_engine):
    with db_engine.begin() as conn:
        command.downgrade(alembic_config(conn), "base")
        assert inspect(conn).get_table_names() == ["alembic_version"]

        command.upgrade(alembic_config(conn), "head")
        assert {"users", "documents", "chunks", "queries"} <= set(inspect(conn).get_table_names())
