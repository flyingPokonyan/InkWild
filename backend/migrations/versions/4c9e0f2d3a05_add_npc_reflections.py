"""add npc_reflections table for long-term NPC memory

Phase 1 NPC reflection — first-person summary per NPC per session, refreshed
when accumulated new memories cross a threshold. Loaded into NPC system
prompt's stable prefix so the NPC has a coherent self-narrative across long
sessions instead of only seeing the last few memory entries.

Revision ID: 4c9e0f2d3a05
Revises: 3b8d9e1c2f04
Create Date: 2026-05-06 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4c9e0f2d3a05"
down_revision: Union[str, Sequence[str], None] = "3b8d9e1c2f04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "npc_reflections" in set(inspector.get_table_names()):
        return

    op.create_table(
        "npc_reflections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("game_sessions.id"),
            nullable=False,
        ),
        sa.Column("npc_name", sa.String(50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("last_memory_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reflection_count", sa.Integer(), nullable=False, server_default="1"),
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
        sa.UniqueConstraint("session_id", "npc_name", name="uq_npc_reflections_session_npc"),
    )
    op.create_index(
        "idx_npc_reflections_session", "npc_reflections", ["session_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "npc_reflections" not in set(inspector.get_table_names()):
        return
    op.drop_index("idx_npc_reflections_session", table_name="npc_reflections")
    op.drop_table("npc_reflections")
