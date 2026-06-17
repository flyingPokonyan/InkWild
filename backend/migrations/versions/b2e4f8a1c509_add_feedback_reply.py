"""add feedback.reply (user-visible admin reply)

Revision ID: b2e4f8a1c509
Revises: a1f3c7d92b40
Create Date: 2026-06-15 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2e4f8a1c509"
down_revision: Union[str, Sequence[str], None] = "a1f3c7d92b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("feedback", sa.Column("reply", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("feedback", "reply")
