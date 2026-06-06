"""credit phase 2: held_units + credit_holds + cached price + gate_fail_mode

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-05-29 18:00:00.000000

Phase 2 of the credits system (see docs/plans/2026-05-29-credits-phase2-hardening-design.md):

* ``credit_wallets.held_units`` — L3 reservation total (available = balance - held).
* ``credit_holds`` — per-action reservation + reliable-settlement outbox.
* ``provider_models.cached_input_price_cents_per_million_tokens`` — cache-aware billing
  (null => bill cache hits at the full input price, i.e. no change).
* ``credit_config.gate_fail_mode`` — 'open' (default) | 'safe' failure posture.

Idempotent: re-running only adds what's missing.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "held_units" not in _cols("credit_wallets"):
        op.add_column(
            "credit_wallets",
            sa.Column("held_units", sa.BigInteger(), nullable=False, server_default="0"),
        )

    if "cached_input_price_cents_per_million_tokens" not in _cols("provider_models"):
        op.add_column(
            "provider_models",
            sa.Column("cached_input_price_cents_per_million_tokens", sa.Integer(), nullable=True),
        )

    if "gate_fail_mode" not in _cols("credit_config"):
        op.add_column(
            "credit_config",
            sa.Column("gate_fail_mode", sa.String(length=8), nullable=False, server_default="open"),
        )

    if "credit_holds" not in _tables():
        op.create_table(
            "credit_holds",
            sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("action", sa.String(length=16), nullable=False),
            sa.Column("ref_type", sa.String(length=16), nullable=True),
            sa.Column("ref_id", sa.String(length=64), nullable=True),
            sa.Column("estimate_units", sa.BigInteger(), nullable=False),
            sa.Column("charged_units", sa.BigInteger(), nullable=True),
            sa.Column("usage_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="held"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("settled_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_credit_holds_user_id", "credit_holds", ["user_id"])
        op.create_index("ix_credit_holds_created_at", "credit_holds", ["created_at"])
        op.create_index("idx_credit_holds_status_created", "credit_holds", ["status", "created_at"])
        op.create_index("idx_credit_holds_user_status", "credit_holds", ["user_id", "status"])


def downgrade() -> None:
    tables = _tables()
    if "credit_holds" in tables:
        op.drop_table("credit_holds")
    if "gate_fail_mode" in _cols("credit_config"):
        op.drop_column("credit_config", "gate_fail_mode")
    if "cached_input_price_cents_per_million_tokens" in _cols("provider_models"):
        op.drop_column("provider_models", "cached_input_price_cents_per_million_tokens")
    if "held_units" in _cols("credit_wallets"):
        op.drop_column("credit_wallets", "held_units")
