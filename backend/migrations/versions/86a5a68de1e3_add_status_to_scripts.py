"""add_status_to_scripts

Revision ID: 86a5a68de1e3
Revises: a1b2c3d4e5f6
Create Date: 2026-05-14 15:56:20.398703

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '86a5a68de1e3'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('scripts', sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'))
    op.execute("UPDATE scripts SET status = 'published' WHERE is_published = TRUE")
    op.create_index('ix_scripts_status', 'scripts', ['status'])
    op.create_index('idx_worlds_status', 'worlds', ['status'])


def downgrade() -> None:
    op.drop_index('idx_worlds_status', table_name='worlds')
    op.drop_index('ix_scripts_status', table_name='scripts')
    op.drop_column('scripts', 'status')
