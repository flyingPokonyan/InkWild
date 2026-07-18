"""world generation workflow persistence

Revision ID: f2a4c6e8b0d1
Revises: e1c9a7b4d2f6
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f2a4c6e8b0d1"
down_revision = "e1c9a7b4d2f6"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("generation_tasks", sa.Column("generation_run_id", sa.Uuid(), nullable=True))
    op.add_column("generation_tasks", sa.Column("root_task_id", sa.Uuid(), nullable=True))
    op.add_column("generation_tasks", sa.Column("parent_task_id", sa.Uuid(), nullable=True))
    op.add_column("generation_tasks", sa.Column("world_spec", JSONB, nullable=True))
    op.add_column("generation_tasks", sa.Column("world_spec_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("generation_tasks", sa.Column("payload_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("generation_tasks", sa.Column("payload_hash", sa.String(64), nullable=True))
    op.create_foreign_key("fk_generation_tasks_parent", "generation_tasks", "generation_tasks", ["parent_task_id"], ["id"])
    for col in ("generation_run_id", "root_task_id", "parent_task_id"):
        op.create_index(f"ix_generation_tasks_{col}", "generation_tasks", [col])

    op.add_column("world_drafts", sa.Column("payload_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("world_drafts", sa.Column("payload_hash", sa.String(64), nullable=True))
    op.add_column("world_drafts", sa.Column("quality_status", sa.String(20), nullable=False, server_default="not_requested"))
    op.create_index("ix_world_drafts_payload_hash", "world_drafts", ["payload_hash"])
    op.create_index("ix_world_drafts_quality_status", "world_drafts", ["quality_status"])

    # Historical rows are completed snapshots; mark them passed during the
    # migration so the recovery worker does not enqueue every old score.
    op.add_column("world_quality_scores", sa.Column("status", sa.String(20), nullable=False, server_default="passed"))
    op.alter_column("world_quality_scores", "status", server_default="pending")
    op.add_column("world_quality_scores", sa.Column("payload_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("world_quality_scores", sa.Column("payload_hash", sa.String(64), nullable=True))
    op.add_column("world_quality_scores", sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("world_quality_scores", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("world_quality_scores", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.add_column("world_quality_scores", sa.Column("finished_at", sa.DateTime(), nullable=True))
    op.create_index("ix_world_quality_scores_status", "world_quality_scores", ["status"])
    op.create_index("ix_world_quality_scores_payload_hash", "world_quality_scores", ["payload_hash"])

    op.create_table(
        "generation_node_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("generation_run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("generation_tasks.id"), nullable=False),
        sa.Column("node_id", sa.String(80), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("spec_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("estimated_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for col in ("generation_run_id", "task_id", "node_id", "status"):
        op.create_index(f"ix_generation_node_runs_{col}", "generation_node_runs", [col])

    op.create_table(
        "generation_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("generation_run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("generation_tasks.id"), nullable=False),
        sa.Column("node_run_id", sa.Uuid(), sa.ForeignKey("generation_node_runs.id"), nullable=True),
        sa.Column("action_type", sa.String(20), nullable=False),
        sa.Column("target_node", sa.String(80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for col in ("generation_run_id", "task_id", "node_run_id", "action_type"):
        op.create_index(f"ix_generation_actions_{col}", "generation_actions", [col])

    op.create_table(
        "generation_violations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("generation_run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("generation_tasks.id"), nullable=False),
        sa.Column("node_run_id", sa.Uuid(), sa.ForeignKey("generation_node_runs.id"), nullable=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("path", sa.String(191), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("repairable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolved_by_action_id", sa.Uuid(), sa.ForeignKey("generation_actions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for col in ("generation_run_id", "task_id", "node_run_id", "code", "severity", "resolved"):
        op.create_index(f"ix_generation_violations_{col}", "generation_violations", [col])


def downgrade() -> None:
    op.drop_table("generation_violations")
    op.drop_table("generation_actions")
    op.drop_table("generation_node_runs")
    op.drop_index("ix_world_quality_scores_payload_hash", table_name="world_quality_scores")
    op.drop_index("ix_world_quality_scores_status", table_name="world_quality_scores")
    for col in ("finished_at", "started_at", "error_message", "attempt", "payload_hash", "payload_revision", "status"):
        op.drop_column("world_quality_scores", col)
    op.drop_index("ix_world_drafts_quality_status", table_name="world_drafts")
    op.drop_index("ix_world_drafts_payload_hash", table_name="world_drafts")
    for col in ("quality_status", "payload_hash", "payload_revision"):
        op.drop_column("world_drafts", col)
    for col in ("parent_task_id", "root_task_id", "generation_run_id"):
        op.drop_index(f"ix_generation_tasks_{col}", table_name="generation_tasks")
    op.drop_constraint("fk_generation_tasks_parent", "generation_tasks", type_="foreignkey")
    for col in ("payload_hash", "payload_revision", "world_spec_version", "world_spec", "parent_task_id", "root_task_id", "generation_run_id"):
        op.drop_column("generation_tasks", col)
