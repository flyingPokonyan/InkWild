"""add admin audit log

Revision ID: 4d6f8a1b3c92
Revises: 2c8b7e5a9d01
Create Date: 2026-04-30 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4d6f8a1b3c92"
down_revision: Union[str, Sequence[str], None] = "2c8b7e5a9d01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "admin_audit_logs" in table_names:
        return

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=191), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_admin_audit_logs_admin_created",
        "admin_audit_logs",
        ["admin_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_admin_audit_logs_resource",
        "admin_audit_logs",
        ["resource_type", "resource_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "admin_audit_logs" not in table_names:
        return

    op.drop_index("idx_admin_audit_logs_resource", table_name="admin_audit_logs")
    op.drop_index("idx_admin_audit_logs_admin_created", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
