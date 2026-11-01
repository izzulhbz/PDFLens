"""Let a logout revoke every copy of a user's session cookie.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-01

Sessions live in a signed cookie, valid until it expires wherever it is.
The cookie now carries users.session_version, which must match on every
request, and logging out increments it. Cookies issued before this
migration carry no version, so everyone logs in once more after upgrading.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "session_version")
