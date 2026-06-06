"""add user creation quota and can_create

Revision ID: be8e4a08d270
Revises: c45bcbdcd049
Create Date: 2026-05-14 16:14:34.487575

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be8e4a08d270'
down_revision: Union[str, Sequence[str], None] = 'c45bcbdcd049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('can_create', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE users SET can_create = TRUE WHERE is_admin = TRUE")

    op.create_table(
        'user_creation_quotas',
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('user_id', sa.Uuid(as_uuid=False), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('quota_date', sa.Date(), nullable=False),
        sa.Column('world_generations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('script_generations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'quota_date', name='uq_user_quota_per_day'),
    )
    op.create_index('idx_user_quota_user_date', 'user_creation_quotas', ['user_id', 'quota_date'])


def downgrade() -> None:
    op.drop_index('idx_user_quota_user_date', table_name='user_creation_quotas')
    op.drop_table('user_creation_quotas')
    op.drop_column('users', 'can_create')
