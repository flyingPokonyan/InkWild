"""add_related_npc_to_memory_entries

Revision ID: f5a2b3c4d6e7
Revises: e4b3c2d1f0a9
Create Date: 2026-04-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f5a2b3c4d6e7"
down_revision: Union[str, Sequence[str], None] = "e4b3c2d1f0a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memory_entries",
        sa.Column("related_npc", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "idx_memory_npc",
        "memory_entries",
        ["session_id", "related_npc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_memory_npc", table_name="memory_entries")
    op.drop_column("memory_entries", "related_npc")
