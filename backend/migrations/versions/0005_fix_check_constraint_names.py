"""Give the CHECK constraints the names the models expect.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-01

The naming convention in app/db.py names CHECK constraints
"ck_<table>_<name>". Migrations 0001-0004 passed names that already had the
prefix, and Alembic applied the convention to them again, so every CHECK
constraint was created as "ck_<table>_ck_<table>_<name>", e.g.
ck_queries_ck_queries_provider_valid. The constraints themselves worked; only
the names were wrong. The model/migration drift check didn't notice because
it ignores CHECK constraints; tests/integration/test_schema.py now checks
their names too.

Earlier migrations are left as they were, so databases that already ran
them and new ones end up identical: both reach this migration with the
doubled names, and it renames them. Future migrations should pass
op.f("ck_<table>_<name>") (a name marked as final) or the bare "<name>".
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, constraint name without the "ck_<table>_" prefix)
_CONSTRAINTS = [
    ("users", "email_lowercase"),
    ("documents", "status_valid"),
    ("documents", "page_count_positive"),
    ("documents", "summary_provider_valid"),
    ("chunks", "chunk_index_non_negative"),
    ("chunks", "page_range_valid"),
    ("queries", "provider_valid"),
    ("queries", "latency_ms_non_negative"),
]


def _rename(doubled_to_correct: bool) -> None:
    for table, name in _CONSTRAINTS:
        correct = f"ck_{table}_{name}"
        doubled = f"ck_{table}_{correct}"
        old, new = (doubled, correct) if doubled_to_correct else (correct, doubled)
        # Fixed names from this file, not user input.
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}")


def upgrade() -> None:
    _rename(doubled_to_correct=True)


def downgrade() -> None:
    # Back to the names 0001-0004 created, so their own downgrades still
    # find the constraints they drop.
    _rename(doubled_to_correct=False)
