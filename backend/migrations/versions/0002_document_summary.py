"""Store a study summary on each document.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01

The summary is one JSON object per document (title, overview, topics,
learning outcomes, key terms). JSONB rather than a set of tables: it is
always read and written as a whole and never queried by its parts, so
splitting it into rows would add joins without any benefit.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("summary", postgresql.JSONB(), nullable=True))
    op.add_column("documents", sa.Column("summary_provider", sa.String(16), nullable=True))
    op.add_column(
        "documents",
        sa.Column("summary_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_documents_summary_provider_valid",
        "documents",
        "summary_provider IS NULL OR summary_provider IN ('anthropic', 'ollama', 'mock')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_documents_summary_provider_valid", "documents", type_="check")
    op.drop_column("documents", "summary_created_at")
    op.drop_column("documents", "summary_provider")
    op.drop_column("documents", "summary")
