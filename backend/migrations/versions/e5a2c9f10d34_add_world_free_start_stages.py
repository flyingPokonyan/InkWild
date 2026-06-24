"""add worlds.free_start_stages

自由模式「人生进度」起点预设（spec docs/plans/2026-06-24-free-start-stages.md）。
可选 JSONB；None = 该世界不提供起点选择，自由模式走老的固定 initial_location 开局。

Revision ID: e5a2c9f10d34
Revises: d4e1f2a3b5c6
Create Date: 2026-06-24 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e5a2c9f10d34"
down_revision: Union[str, Sequence[str], None] = "d4e1f2a3b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "worlds",
        sa.Column(
            "free_start_stages",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("worlds", "free_start_stages")
