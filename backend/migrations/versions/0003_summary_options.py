"""Record the settings each summary was written with.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01

Users can choose the tone, length and charts of their summaries. Storing
the choice next to the summary lets the UI tell when a saved summary no
longer matches the user's current settings, and offer to regenerate it.
NULL for summaries written before this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("summary_options", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "summary_options")
