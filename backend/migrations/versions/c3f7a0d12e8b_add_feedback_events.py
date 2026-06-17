"""add feedback_events timeline

Revision ID: c3f7a0d12e8b
Revises: b2e4f8a1c509
Create Date: 2026-06-15 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3f7a0d12e8b"
down_revision: Union[str, Sequence[str], None] = "b2e4f8a1c509"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback_events",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("feedback_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["feedback_id"], ["feedback.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_feedback_events_fb", "feedback_events", ["feedback_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_feedback_events_fb", table_name="feedback_events")
    op.drop_table("feedback_events")
