"""add_missing_indexes

Revision ID: 8a2b1c3d4e5f
Revises: 7f2c3d4e5a08
Create Date: 2026-05-08 00:00:00.000000

Adds two indexes to support hot read paths surfaced during Phase 2 query
review:

* ``idx_game_sessions_world_id`` — speeds up admin / analytics joins that
  group sessions by ``world_id`` (e.g. cost-per-world dashboards) and
  per-world fan-out queries when a world is unpublished.
* ``idx_messages_session_role`` — speeds up history filters that pull
  only ``user`` or ``assistant`` rows for a given session (replay,
  context rebuild, exporter).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a2b1c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "7f2c3d4e5a08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    game_session_indexes = _existing_indexes("game_sessions")
    if "idx_game_sessions_world_id" not in game_session_indexes:
        op.create_index(
            "idx_game_sessions_world_id",
            "game_sessions",
            ["world_id"],
            unique=False,
        )

    message_indexes = _existing_indexes("messages")
    if "idx_messages_session_role" not in message_indexes:
        op.create_index(
            "idx_messages_session_role",
            "messages",
            ["session_id", "role"],
            unique=False,
        )


def downgrade() -> None:
    message_indexes = _existing_indexes("messages")
    if "idx_messages_session_role" in message_indexes:
        op.drop_index("idx_messages_session_role", table_name="messages")

    game_session_indexes = _existing_indexes("game_sessions")
    if "idx_game_sessions_world_id" in game_session_indexes:
        op.drop_index("idx_game_sessions_world_id", table_name="game_sessions")
