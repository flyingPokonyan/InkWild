"""add world_characters.initial_peer_relations

NPC-2 — JSON list of {target, trust, label, history_summary} written by the
world creator agent. Seeded into ``npc_relations`` (both directions) when a
session starts. Nullable so legacy worlds keep working.

Revision ID: 7f2c3d4e5a08
Revises: 6e1b2c3d4f07
Create Date: 2026-05-07 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f2c3d4e5a08"
down_revision: Union[str, Sequence[str], None] = "6e1b2c3d4f07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("world_characters")}
    if "initial_peer_relations" not in columns:
        op.add_column(
            "world_characters",
            sa.Column("initial_peer_relations", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("world_characters")}
    if "initial_peer_relations" in columns:
        op.drop_column("world_characters", "initial_peer_relations")
