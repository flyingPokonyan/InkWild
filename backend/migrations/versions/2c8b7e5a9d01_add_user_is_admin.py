"""add user is_admin

Revision ID: 2c8b7e5a9d01
Revises: 6f1c2a4b8d9e
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2c8b7e5a9d01"
down_revision: Union[str, Sequence[str], None] = "6f1c2a4b8d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_admin" in user_columns:
        return

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))

    if bind.dialect.name != "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column("is_admin", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_admin" not in user_columns:
        return

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_admin")
