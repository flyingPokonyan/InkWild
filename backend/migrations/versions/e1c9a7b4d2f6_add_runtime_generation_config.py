"""add runtime generation config

Revision ID: e1c9a7b4d2f6
Revises: d8f4a6b2c1e9
Create Date: 2026-07-09 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1c9a7b4d2f6"
down_revision: Union[str, Sequence[str], None] = "d8f4a6b2c1e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_config",
        sa.Column("llm_global_concurrency", sa.Integer(), nullable=False, server_default="1000"),
    )
    op.add_column(
        "system_config",
        sa.Column("llm_call_timeout_seconds", sa.Float(), nullable=False, server_default="120"),
    )
    op.add_column(
        "system_config",
        sa.Column("llm_call_max_retries", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "system_config",
        sa.Column("llm_call_retry_backoff_seconds", sa.Float(), nullable=False, server_default="3"),
    )
    op.add_column(
        "system_config",
        sa.Column("generation_task_active_limit_per_user", sa.Integer(), nullable=False, server_default="10"),
    )
    op.add_column(
        "system_config",
        sa.Column("image_generation_concurrency", sa.Integer(), nullable=False, server_default="6"),
    )
    op.add_column(
        "system_config",
        sa.Column("image_generation_global_concurrency", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "system_config",
        sa.Column("image_generation_timeout_seconds", sa.Float(), nullable=False, server_default="100"),
    )
    op.add_column(
        "system_config",
        sa.Column("image_generation_quality", sa.String(length=16), nullable=False, server_default="high"),
    )
    op.add_column(
        "system_config",
        sa.Column("lore_pack_concurrency", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column(
        "system_config",
        sa.Column("character_batch_concurrency", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column(
        "system_config",
        sa.Column("events_data_concurrency", sa.Integer(), nullable=False, server_default="3"),
    )


def downgrade() -> None:
    op.drop_column("system_config", "events_data_concurrency")
    op.drop_column("system_config", "character_batch_concurrency")
    op.drop_column("system_config", "lore_pack_concurrency")
    op.drop_column("system_config", "image_generation_quality")
    op.drop_column("system_config", "image_generation_timeout_seconds")
    op.drop_column("system_config", "image_generation_global_concurrency")
    op.drop_column("system_config", "image_generation_concurrency")
    op.drop_column("system_config", "generation_task_active_limit_per_user")
    op.drop_column("system_config", "llm_call_retry_backoff_seconds")
    op.drop_column("system_config", "llm_call_max_retries")
    op.drop_column("system_config", "llm_call_timeout_seconds")
    op.drop_column("system_config", "llm_global_concurrency")
