"""add generation tasks

Revision ID: 9d1a2b3c4d5e
Revises: 7b9e4a1d2c3f, f5a2b3c4d6e7
Create Date: 2026-04-13 17:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = ("7b9e4a1d2c3f", "f5a2b3c4d6e7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "generation_tasks" not in table_names:
        op.create_table(
            "generation_tasks",
            sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("draft_type", sa.String(length=20), nullable=False),
            sa.Column("draft_id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("request_payload", sa.JSON(), nullable=False),
            sa.Column("current_phase", sa.String(length=50), nullable=True),
            sa.Column("current_code", sa.String(length=50), nullable=True),
            sa.Column("current_message", sa.Text(), nullable=True),
            sa.Column("last_event_seq", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_generation_tasks_draft_id", "generation_tasks", ["draft_id"], unique=False)
        op.create_index("idx_generation_tasks_status", "generation_tasks", ["status"], unique=False)

    if "generation_task_events" not in table_names:
        op.create_table(
            "generation_task_events",
            sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("task_id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("event_name", sa.String(length=20), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["generation_tasks.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_generation_task_events_task_id", "generation_task_events", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_generation_task_events_task_id", table_name="generation_task_events")
    op.drop_table("generation_task_events")
    op.drop_index("idx_generation_tasks_status", table_name="generation_tasks")
    op.drop_index("idx_generation_tasks_draft_id", table_name="generation_tasks")
    op.drop_table("generation_tasks")
