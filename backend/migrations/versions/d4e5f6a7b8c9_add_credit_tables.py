"""add credit wallet / ledger / config tables (+ backfill existing users)

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-05-29 16:30:00.000000

Phase 1 of the credits system (see docs/plans/2026-05-29-credits-phase1-design.md):

* ``credit_wallets`` — per-user cached balance (units; 1 credit = 10000 units).
* ``credit_ledger`` — append-only credit movements (grants + per-action debits).
* ``credit_config`` — singleton (id=1) admin-editable economy config.

Backfill: seed the config singleton + give every existing user a wallet with
the signup grant, recorded as a ``backfill_grant`` ledger row. Idempotent —
re-running only touches users that still lack a wallet.
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirror model defaults (units = credits * 10000).
_UNIT_SCALE = 10_000
_SIGNUP_GRANT_UNITS = 500 * _UNIT_SCALE
_ESTIMATE_GAME_UNITS = 25 * _UNIT_SCALE
_ESTIMATE_WORLD_UNITS = 70 * _UNIT_SCALE
_ESTIMATE_SCRIPT_UNITS = 200 * _UNIT_SCALE


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()

    if "credit_wallets" not in tables:
        op.create_table(
            "credit_wallets",
            sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("balance_units", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("lifetime_granted_units", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("lifetime_spent_units", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", name="uq_credit_wallets_user"),
        )
        op.create_index("idx_credit_wallets_user", "credit_wallets", ["user_id"])

    if "credit_ledger" not in tables:
        op.create_table(
            "credit_ledger",
            sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("delta_units", sa.BigInteger(), nullable=False),
            sa.Column("balance_after_units", sa.BigInteger(), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("category", sa.String(length=16), nullable=True),
            sa.Column("ref_type", sa.String(length=16), nullable=True),
            sa.Column("ref_id", sa.String(length=64), nullable=True),
            sa.Column("cost_cents", sa.Integer(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("actor_user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_credit_ledger_user", "credit_ledger", ["user_id"])
        op.create_index("idx_credit_ledger_created", "credit_ledger", ["created_at"])
        op.create_index("idx_credit_ledger_user_created", "credit_ledger", ["user_id", "created_at"])

    if "credit_config" not in tables:
        op.create_table(
            "credit_config",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("billing_multiplier_milli", sa.Integer(), nullable=False, server_default="1000"),
            sa.Column("signup_grant_units", sa.BigInteger(), nullable=False, server_default=str(_SIGNUP_GRANT_UNITS)),
            sa.Column("estimate_game_units", sa.BigInteger(), nullable=False, server_default=str(_ESTIMATE_GAME_UNITS)),
            sa.Column("estimate_world_units", sa.BigInteger(), nullable=False, server_default=str(_ESTIMATE_WORLD_UNITS)),
            sa.Column("estimate_script_units", sa.BigInteger(), nullable=False, server_default=str(_ESTIMATE_SCRIPT_UNITS)),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    bind = op.get_bind()

    # Seed the singleton config row (id=1).
    bind.execute(
        sa.text(
            "INSERT INTO credit_config "
            "(id, billing_multiplier_milli, signup_grant_units, estimate_game_units, "
            " estimate_world_units, estimate_script_units, updated_at) "
            "VALUES (1, 1000, :g, :eg, :ew, :es, now()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "g": _SIGNUP_GRANT_UNITS,
            "eg": _ESTIMATE_GAME_UNITS,
            "ew": _ESTIMATE_WORLD_UNITS,
            "es": _ESTIMATE_SCRIPT_UNITS,
        },
    )

    # Backfill: wallet + signup grant for every user that lacks a wallet.
    rows = bind.execute(
        sa.text(
            "SELECT id FROM users WHERE id NOT IN (SELECT user_id FROM credit_wallets)"
        )
    ).fetchall()
    for (user_id,) in rows:
        grant = _SIGNUP_GRANT_UNITS
        bind.execute(
            sa.text(
                "INSERT INTO credit_wallets "
                "(id, user_id, balance_units, lifetime_granted_units, lifetime_spent_units, created_at, updated_at) "
                "VALUES (:id, :uid, :g, :g, 0, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "uid": str(user_id), "g": grant},
        )
        bind.execute(
            sa.text(
                "INSERT INTO credit_ledger "
                "(id, user_id, delta_units, balance_after_units, kind, category, created_at) "
                "VALUES (:id, :uid, :g, :g, 'backfill_grant', 'grant', now())"
            ),
            {"id": str(uuid.uuid4()), "uid": str(user_id), "g": grant},
        )


def downgrade() -> None:
    tables = _tables()
    if "credit_ledger" in tables:
        op.drop_table("credit_ledger")
    if "credit_wallets" in tables:
        op.drop_table("credit_wallets")
    if "credit_config" in tables:
        op.drop_table("credit_config")
