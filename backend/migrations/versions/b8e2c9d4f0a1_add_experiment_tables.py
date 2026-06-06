"""add experiment dashboard tables

Revision ID: b8e2c9d4f0a1
Revises: a7c4f2b8e1d9
Create Date: 2026-05-22 13:25:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e2c9d4f0a1"
down_revision: Union[str, Sequence[str], None] = "a7c4f2b8e1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()

    if "experiment_runs" not in tables:
        op.create_table(
            "experiment_runs",
            sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column("experiment_id", sa.String(length=80), nullable=False),
            sa.Column("world_id", sa.Uuid(as_uuid=False), sa.ForeignKey("worlds.id"), nullable=True),
            sa.Column("generation_task_id", sa.Uuid(as_uuid=False), sa.ForeignKey("generation_tasks.id"), nullable=True),
            sa.Column("session_id", sa.Uuid(as_uuid=False), sa.ForeignKey("game_sessions.id"), nullable=True),
            sa.Column("world_source_layer", sa.String(length=2), nullable=True),
            sa.Column("world_source_label", sa.String(length=200), nullable=True),
            sa.Column("mode", sa.String(length=20), nullable=True),
            sa.Column("player_archetype", sa.String(length=20), nullable=True),
            sa.Column("player_model", sa.String(length=120), nullable=True),
            sa.Column("seed", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "experiment_id",
                "world_id",
                "mode",
                "player_archetype",
                "player_model",
                "seed",
                name="uq_experiment_runs_combo",
            ),
        )
        op.create_index("ix_experiment_runs_experiment_id", "experiment_runs", ["experiment_id"])
        op.create_index("ix_experiment_runs_status", "experiment_runs", ["status"])
        op.create_index("idx_experiment_runs_experiment_status", "experiment_runs", ["experiment_id", "status"])
        op.create_index("idx_experiment_runs_world", "experiment_runs", ["world_id"])
        op.create_index("idx_experiment_runs_session", "experiment_runs", ["session_id"])

    if "experiment_world_tier1_scores" not in tables:
        op.create_table(
            "experiment_world_tier1_scores",
            sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column("experiment_id", sa.String(length=80), nullable=False),
            sa.Column("world_id", sa.Uuid(as_uuid=False), sa.ForeignKey("worlds.id"), nullable=False),
            sa.Column("generation_task_id", sa.Uuid(as_uuid=False), sa.ForeignKey("generation_tasks.id"), nullable=True),
            sa.Column("source_layer", sa.String(length=2), nullable=False),
            sa.Column("source_label", sa.String(length=200), nullable=False),
            sa.Column("attempt", sa.Integer(), nullable=False),
            sa.Column("scores", sa.JSON(), nullable=False),
            sa.Column("total", sa.Float(), nullable=False),
            sa.Column("reasoning", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("retried", sa.Boolean(), nullable=False),
            sa.Column("retry_reasoning", sa.Text(), nullable=True),
            sa.Column("judge_model", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("experiment_id", "world_id", "attempt", name="uq_experiment_tier1_world_attempt"),
        )
        op.create_index("ix_experiment_world_tier1_scores_experiment_id", "experiment_world_tier1_scores", ["experiment_id"])
        op.create_index("idx_experiment_tier1_experiment", "experiment_world_tier1_scores", ["experiment_id"])
        op.create_index("idx_experiment_tier1_world", "experiment_world_tier1_scores", ["world_id"])

    if "experiment_session_tier2_scores" not in tables:
        op.create_table(
            "experiment_session_tier2_scores",
            sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column("experiment_id", sa.String(length=80), nullable=False),
            sa.Column("session_id", sa.Uuid(as_uuid=False), sa.ForeignKey("game_sessions.id"), nullable=False),
            sa.Column("world_id", sa.Uuid(as_uuid=False), sa.ForeignKey("worlds.id"), nullable=False),
            sa.Column("judge_model", sa.String(length=120), nullable=False),
            sa.Column("scores", sa.JSON(), nullable=False),
            sa.Column("total_weighted", sa.Float(), nullable=False),
            sa.Column("issues_noted", sa.JSON(), nullable=False),
            sa.Column("exemplar_quote", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("experiment_id", "session_id", name="uq_experiment_tier2_session"),
        )
        op.create_index("ix_experiment_session_tier2_scores_experiment_id", "experiment_session_tier2_scores", ["experiment_id"])
        op.create_index("idx_experiment_tier2_experiment", "experiment_session_tier2_scores", ["experiment_id"])
        op.create_index("idx_experiment_tier2_world", "experiment_session_tier2_scores", ["world_id"])

    if "experiment_turn_tags" not in tables:
        op.create_table(
            "experiment_turn_tags",
            sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column("experiment_id", sa.String(length=80), nullable=False),
            sa.Column("session_id", sa.Uuid(as_uuid=False), sa.ForeignKey("game_sessions.id"), nullable=False),
            sa.Column("turn_id", sa.Integer(), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("issues_noted", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("experiment_id", "session_id", "turn_id", name="uq_experiment_turn_tag"),
        )
        op.create_index("ix_experiment_turn_tags_experiment_id", "experiment_turn_tags", ["experiment_id"])
        op.create_index("idx_experiment_turn_tags_experiment", "experiment_turn_tags", ["experiment_id"])
        op.create_index("idx_experiment_turn_tags_session", "experiment_turn_tags", ["session_id"])

    if "experiment_alerts" not in tables:
        op.create_table(
            "experiment_alerts",
            sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column("experiment_id", sa.String(length=80), nullable=False),
            sa.Column("level", sa.String(length=20), nullable=False),
            sa.Column("icon", sa.String(length=30), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("target", sa.String(length=191), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_experiment_alerts_experiment_id", "experiment_alerts", ["experiment_id"])
        op.create_index("idx_experiment_alerts_experiment_created", "experiment_alerts", ["experiment_id", "created_at"])

    if "experiment_session_reviews" not in tables:
        op.create_table(
            "experiment_session_reviews",
            sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column("experiment_id", sa.String(length=80), nullable=False),
            sa.Column("session_id", sa.Uuid(as_uuid=False), sa.ForeignKey("game_sessions.id"), nullable=False),
            sa.Column("verdict", sa.String(length=20), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("reviewed_by_user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("experiment_id", "session_id", name="uq_experiment_session_review"),
        )
        op.create_index("ix_experiment_session_reviews_experiment_id", "experiment_session_reviews", ["experiment_id"])
        op.create_index("idx_experiment_reviews_experiment", "experiment_session_reviews", ["experiment_id"])


def downgrade() -> None:
    for table_name in (
        "experiment_session_reviews",
        "experiment_alerts",
        "experiment_turn_tags",
        "experiment_session_tier2_scores",
        "experiment_world_tier1_scores",
        "experiment_runs",
    ):
        if table_name in _tables():
            op.drop_table(table_name)
