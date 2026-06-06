"""token_usage cache_hit_tokens + cache_miss_tokens

Revision ID: c1d2e3f4a5b6
Revises: 71360de985b8
Create Date: 2026-05-29 15:05:00.000000

Persist the DeepSeek-style prefix-cache split that the providers already
surface (``cache_hit_tokens`` / ``cache_miss_tokens`` on the usage event)
and that ``usage_recorder`` previously only logged to structlog. Lets the
per-stage latency/cost measurement — and admin analytics — see how much
of each turn's Director / NPC / Narrator input was served from cache.

* ``cache_hit_tokens`` integer NULL.
* ``cache_miss_tokens`` integer NULL.

Both nullable on purpose: NULL = provider didn't report cache stats
(unsupported), distinct from a reported 0 (cache cold). Existing rows
backfill to NULL — true at the time they were written, since nothing was
persisting cache stats then. ``cost_cents`` is intentionally left as-is;
re-rating cache-hit tokens at the discounted price is a separate follow-up
gated on observing real hit rates.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "71360de985b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _existing_columns("token_usage")
    if "cache_hit_tokens" not in columns:
        op.add_column(
            "token_usage",
            sa.Column("cache_hit_tokens", sa.Integer(), nullable=True),
        )
    if "cache_miss_tokens" not in columns:
        op.add_column(
            "token_usage",
            sa.Column("cache_miss_tokens", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    columns = _existing_columns("token_usage")
    if "cache_miss_tokens" in columns:
        op.drop_column("token_usage", "cache_miss_tokens")
    if "cache_hit_tokens" in columns:
        op.drop_column("token_usage", "cache_hit_tokens")
