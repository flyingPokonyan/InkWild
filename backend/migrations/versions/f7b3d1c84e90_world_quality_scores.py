"""world_quality_scores: 异步生成质量打分快照

Revision ID: f7b3d1c84e90
Revises: e5a2c9f10d34
Create Date: 2026-06-24

plan: docs/plans/2026-06-24-generation-agentic-loop.md
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "f7b3d1c84e90"
down_revision = "e5a2c9f10d34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "world_quality_scores",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("task_id", sa.Uuid(as_uuid=False), sa.ForeignKey("generation_tasks.id"), nullable=False),
        sa.Column("draft_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="world"),
        sa.Column("character_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("playable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("must_have_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("must_have_covered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shared_events_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("structure_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("soft_ip_consistency", sa.Integer(), nullable=True),
        sa.Column("soft_collision", sa.Integer(), nullable=True),
        sa.Column("soft_tension", sa.Integer(), nullable=True),
        sa.Column("soft_summary", sa.Text(), nullable=True),
        sa.Column("backfill_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prune_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("soft_warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overall_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("detail", JSONB(), nullable=True),
        sa.Column("scored_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_world_quality_scores_task_id", "world_quality_scores", ["task_id"])
    op.create_index("ix_world_quality_scores_draft_id", "world_quality_scores", ["draft_id"])
    op.create_index("ix_world_quality_scores_overall_score", "world_quality_scores", ["overall_score"])


def downgrade() -> None:
    op.drop_index("ix_world_quality_scores_overall_score", table_name="world_quality_scores")
    op.drop_index("ix_world_quality_scores_draft_id", table_name="world_quality_scores")
    op.drop_index("ix_world_quality_scores_task_id", table_name="world_quality_scores")
    op.drop_table("world_quality_scores")
