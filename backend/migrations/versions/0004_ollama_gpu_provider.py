"""Allow "ollama_gpu" as the provider of an answer or summary.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01

A second local provider, a larger model on an Ollama that runs natively on
the host and can use its GPU. The provider columns are guarded by CHECK
constraints listing the allowed names, so the new name must be added to
both. Postgres can't alter a CHECK constraint in place: it is dropped and
recreated, inside the migration's transaction.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS = [
    # (constraint, table, column)
    ("ck_queries_provider_valid", "queries", "provider"),
    ("ck_documents_summary_provider_valid", "documents", "summary_provider"),
]


def _replace(names: str) -> None:
    for constraint, table, column in _CONSTRAINTS:
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(constraint, table, f"{column} IS NULL OR {column} IN ({names})")


def upgrade() -> None:
    _replace("'anthropic', 'ollama_gpu', 'ollama', 'mock'")


def downgrade() -> None:
    # Fails if any row already records "ollama_gpu", rather than losing it.
    _replace("'anthropic', 'ollama', 'mock'")
