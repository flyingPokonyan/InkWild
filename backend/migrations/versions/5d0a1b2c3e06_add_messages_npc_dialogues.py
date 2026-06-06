"""add messages.npc_dialogues for NPC voice-anchor recall

Phase 1.B.4 — per-NPC raw dialogue stored alongside the assistant message
so the NPC agent can be re-fed its own last few utterances and stay in
character across long sessions. JSON keeps schema portable across PG/SQLite.

Revision ID: 5d0a1b2c3e06
Revises: 4c9e0f2d3a05
Create Date: 2026-05-06 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5d0a1b2c3e06"
down_revision: Union[str, Sequence[str], None] = "4c9e0f2d3a05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("messages")}
    if "npc_dialogues" not in columns:
        op.add_column(
            "messages",
            sa.Column("npc_dialogues", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("messages")}
    if "npc_dialogues" in columns:
        op.drop_column("messages", "npc_dialogues")
