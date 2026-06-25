"""world_quality_scores: 软评门控字段 blocking_flags + shippable

Revision ID: c9d2e4f6a1b8
Revises: f7b3d1c84e90
Create Date: 2026-06-25

plan: docs/plans/2026-06-25-generation-quality-loop-reopen.md (P0 两数门控替 cap-to-55)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "c9d2e4f6a1b8"
down_revision = "f7b3d1c84e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "world_quality_scores",
        sa.Column("blocking_flags", JSONB(), nullable=True),
    )
    op.add_column(
        "world_quality_scores",
        sa.Column("shippable", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_world_quality_scores_shippable", "world_quality_scores", ["shippable"]
    )


def downgrade() -> None:
    op.drop_index("ix_world_quality_scores_shippable", table_name="world_quality_scores")
    op.drop_column("world_quality_scores", "shippable")
    op.drop_column("world_quality_scores", "blocking_flags")
