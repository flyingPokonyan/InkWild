"""expand token_usage.provider length

Revision ID: d8f4a6b2c1e9
Revises: c9d2e4f6a1b8
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa


revision = "d8f4a6b2c1e9"
down_revision = "c9d2e4f6a1b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "token_usage",
        "provider",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "token_usage",
        "provider",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
