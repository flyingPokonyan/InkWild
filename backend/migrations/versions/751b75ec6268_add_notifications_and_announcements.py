"""add notifications and announcements

Revision ID: 751b75ec6268
Revises: 757e92842328
Create Date: 2026-06-05 07:43:02.498531

Note: autogenerate surfaced a lot of pre-existing model/DB drift (credit/npc/
experiment index renames, type changes). Those are intentionally NOT included
here — this migration only adds the three new notification tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '751b75ec6268'
down_revision: Union[str, Sequence[str], None] = '757e92842328'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'announcements',
        sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('level', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_announcements_status_pub', 'announcements', ['status', 'published_at'], unique=False)

    op.create_table(
        'notifications',
        sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('user_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('link', sa.String(length=500), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_notifications_user_created', 'notifications', ['user_id', 'created_at'], unique=False)
    op.create_index('idx_notifications_user_unread', 'notifications', ['user_id', 'read_at'], unique=False)

    op.create_table(
        'announcement_reads',
        sa.Column('user_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('announcement_id', sa.Uuid(as_uuid=False), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['announcement_id'], ['announcements.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('user_id', 'announcement_id'),
    )


def downgrade() -> None:
    op.drop_table('announcement_reads')
    op.drop_index('idx_notifications_user_unread', table_name='notifications')
    op.drop_index('idx_notifications_user_created', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index('idx_announcements_status_pub', table_name='announcements')
    op.drop_table('announcements')
