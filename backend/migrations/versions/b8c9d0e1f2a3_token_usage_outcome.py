"""token_usage outcome + retry_count

Revision ID: b8c9d0e1f2a3
Revises: a7c4f2b8e1d9
Create Date: 2026-05-23 12:00:00.000000

Phase 9 of the generation/runtime hardening plan
(``docs/plans/generation-runtime-hardening-2026-05.md``).

Adds two columns to ``token_usage`` so the Director can record whether a
turn's LLM call succeeded on the first try, succeeded after a retry, or
failed parsing entirely. Lets the admin dashboard compute per-model
parse-failure rate so model swaps can be evaluated against gameplay
stability data instead of vibes.

* ``outcome`` varchar(20) NOT NULL default ``'success'``.
  Values used today: success / retried_success / parse_failure / error.
  Enforcement is at the application sink (not a CHECK constraint) so
  adding a new bucket later doesn't need a migration.
* ``retry_count`` integer NOT NULL default 0.

Existing rows backfill to ``outcome='success'`` / ``retry_count=0`` via
the server_default — true at the time those rows were written.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7c4f2b8e1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _existing_columns("token_usage")
    if "outcome" not in columns:
        op.add_column(
            "token_usage",
            sa.Column(
                "outcome",
                sa.String(length=20),
                nullable=False,
                server_default="success",
            ),
        )
    if "retry_count" not in columns:
        op.add_column(
            "token_usage",
            sa.Column(
                "retry_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    columns = _existing_columns("token_usage")
    if "retry_count" in columns:
        op.drop_column("token_usage", "retry_count")
    if "outcome" in columns:
        op.drop_column("token_usage", "outcome")
