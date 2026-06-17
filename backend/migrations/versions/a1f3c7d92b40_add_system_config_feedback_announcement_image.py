"""add system_config, feedback, announcement image_url

Revision ID: a1f3c7d92b40
Revises: 751b75ec6268
Create Date: 2026-06-15 09:00:00.000000

上线前三功能的 schema：
- system_config 单例表（注册放量配置）
- announcements.image_url（公告配图）
- feedback 表（用户反馈）

只新增本批改动；不带 autogenerate 扫出的历史 drift。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1f3c7d92b40"
down_revision: Union[str, Sequence[str], None] = "751b75ec6268"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_config",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("signup_mode", sa.String(length=16), nullable=False),
        sa.Column("signup_cap", sa.Integer(), nullable=False),
        sa.Column("signup_batch_start", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("announcements", sa.Column("image_url", sa.String(length=500), nullable=True))

    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("page_url", sa.String(length=500), nullable=True),
        sa.Column("contact", sa.String(length=200), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_feedback_status_created", "feedback", ["status", "created_at"], unique=False)
    op.create_index("idx_feedback_user_created", "feedback", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_feedback_user_created", table_name="feedback")
    op.drop_index("idx_feedback_status_created", table_name="feedback")
    op.drop_table("feedback")
    op.drop_column("announcements", "image_url")
    op.drop_table("system_config")
