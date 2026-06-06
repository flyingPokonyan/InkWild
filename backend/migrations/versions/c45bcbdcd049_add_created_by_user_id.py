"""add created_by_user_id

Revision ID: c45bcbdcd049
Revises: 86a5a68de1e3
Create Date: 2026-05-14 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c45bcbdcd049'
down_revision = '86a5a68de1e3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT id FROM users WHERE is_admin = TRUE ORDER BY created_at LIMIT 1"))
    admin_row = result.first()
    if not admin_row:
        raise Exception("Migration requires at least 1 admin user (users.is_admin=TRUE). Create one first.")
    admin_id = admin_row[0]

    # Step 1: drafts and generation_tasks — add nullable, backfill, set NOT NULL
    for tbl in ('world_drafts', 'script_drafts', 'generation_tasks'):
        op.add_column(tbl, sa.Column('created_by_user_id', sa.Uuid(as_uuid=False), nullable=True))
        conn.execute(sa.text(f"UPDATE {tbl} SET created_by_user_id = :uid WHERE created_by_user_id IS NULL"), {"uid": admin_id})
        op.alter_column(tbl, 'created_by_user_id', nullable=False)
        op.create_foreign_key(f'fk_{tbl}_user', tbl, 'users', ['created_by_user_id'], ['id'])
        op.create_index(f'idx_{tbl}_user', tbl, ['created_by_user_id'])

    # Step 2: worlds and scripts — nullable (NULL = official/seed)
    for tbl in ('worlds', 'scripts'):
        op.add_column(tbl, sa.Column('created_by_user_id', sa.Uuid(as_uuid=False), nullable=True))
        op.create_foreign_key(f'fk_{tbl}_user', tbl, 'users', ['created_by_user_id'], ['id'])
        op.create_index(f'idx_{tbl}_user', tbl, ['created_by_user_id'])


def downgrade() -> None:
    for tbl in ('scripts', 'worlds', 'generation_tasks', 'script_drafts', 'world_drafts'):
        op.drop_index(f'idx_{tbl}_user', table_name=tbl)
        op.drop_constraint(f'fk_{tbl}_user', tbl, type_='foreignkey')
        op.drop_column(tbl, 'created_by_user_id')
