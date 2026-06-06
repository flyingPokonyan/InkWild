"""add memory_entries table

Revision ID: 8c4c7c1d2c41
Revises: 472da503b7df
Create Date: 2026-04-08 16:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8c4c7c1d2c41"
down_revision: Union[str, Sequence[str], None] = "472da503b7df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("memory_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("importance", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_memory_session", "memory_entries", ["session_id"], unique=False)
    op.create_index("idx_memory_session_type", "memory_entries", ["session_id", "memory_type"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_memory_session_type", table_name="memory_entries")
    op.drop_index("idx_memory_session", table_name="memory_entries")
    op.drop_table("memory_entries")
