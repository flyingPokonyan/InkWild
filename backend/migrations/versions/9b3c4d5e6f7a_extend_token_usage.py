"""extend token usage

Revision ID: 9b3c4d5e6f7a
Revises: 8a2b1c3d4e5f
Create Date: 2026-05-08 00:05:00.000000

Phase 2 token-usage enrichment. Adds two nullable columns so cost
guardrail / analytics can resolve the *full* model identity behind a
recorded turn:

* ``model_id``      — the slot-bound provider model id (e.g.
  ``claude-sonnet-4-5-20250929``). The legacy ``model`` column still
  holds the short name for backwards compat.
* ``provider_name`` — the slot-bound provider display name (e.g.
  ``Anthropic-Production``). The legacy ``provider`` column still holds
  the short type (``claude`` / ``deepseek`` / ``grok`` / ``openai`` /
  ``gemini``).

Note: the original Phase 2.D.1 spec also listed ``input_tokens`` and
``output_tokens`` as columns to add. Both already exist on the
``token_usage`` table from the initial schema and are NOT NULL — they
are populated on every turn. This migration is therefore a no-op for
those two columns.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b3c4d5e6f7a"
down_revision: Union[str, Sequence[str], None] = "8a2b1c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _existing_columns("token_usage")
    if "model_id" not in columns:
        op.add_column(
            "token_usage",
            sa.Column("model_id", sa.String(length=255), nullable=True),
        )
    if "provider_name" not in columns:
        op.add_column(
            "token_usage",
            sa.Column("provider_name", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    columns = _existing_columns("token_usage")
    if "provider_name" in columns:
        op.drop_column("token_usage", "provider_name")
    if "model_id" in columns:
        op.drop_column("token_usage", "model_id")
