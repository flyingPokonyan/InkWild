"""add npc_relations table for persistent NPC↔NPC relations

NPC-2 (group interaction) — directed (A→B and B→A separate rows; trust may be
asymmetric). Seeded at session start from
``world_characters.initial_peer_relations``. NPC-3 (background simulation)
will mutate these rows later; NPC-2 only reads.

Revision ID: 6e1b2c3d4f07
Revises: 5d0a1b2c3e06
Create Date: 2026-05-07 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6e1b2c3d4f07"
down_revision: Union[str, Sequence[str], None] = "5d0a1b2c3e06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "npc_relations" in set(inspector.get_table_names()):
        return

    op.create_table(
        "npc_relations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("game_sessions.id"),
            nullable=False,
        ),
        sa.Column("npc_a", sa.String(50), nullable=False),
        sa.Column("npc_b", sa.String(50), nullable=False),
        sa.Column("trust", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("relationship_label", sa.String(50), nullable=True),
        sa.Column("history_summary", sa.Text(), nullable=True),
        sa.Column("last_event_round", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "session_id", "npc_a", "npc_b", name="uq_npc_relations_session_pair"
        ),
    )
    op.create_index(
        "idx_npc_relations_session_a",
        "npc_relations",
        ["session_id", "npc_a"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "npc_relations" not in set(inspector.get_table_names()):
        return
    op.drop_index("idx_npc_relations_session_a", table_name="npc_relations")
    op.drop_table("npc_relations")
