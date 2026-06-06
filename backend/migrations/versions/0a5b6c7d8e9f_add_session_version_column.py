"""add session version column

Revision ID: 0a5b6c7d8e9f
Revises: 7e1a9c0d4b2f
Create Date: 2026-04-30 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0a5b6c7d8e9f"
down_revision: Union[str, Sequence[str], None] = "7e1a9c0d4b2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("game_sessions")}
    if "version" in columns:
        return

    op.add_column(
        "game_sessions",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("game_sessions")}
    if "version" not in columns:
        return

    op.drop_column("game_sessions", "version")
