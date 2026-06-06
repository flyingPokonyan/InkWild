"""add ip_knowledge_packs

Revision ID: 12d373a9cd9e
Revises: 58f13b75b16c
Create Date: 2026-05-14 07:08:20.395617

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '12d373a9cd9e'
down_revision: Union[str, Sequence[str], None] = '58f13b75b16c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('ip_knowledge_packs',
    sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('world_id', sa.Uuid(as_uuid=False), nullable=True),
    sa.Column('draft_id', sa.Uuid(as_uuid=False), nullable=True),
    sa.Column('ip_name', sa.String(length=200), nullable=False),
    sa.Column('fidelity_mode', sa.String(length=20), nullable=False),
    sa.Column('pack_json', sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['draft_id'], ['world_drafts.id'], ),
    sa.ForeignKeyConstraint(['world_id'], ['worlds.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ip_knowledge_packs_draft_id'), 'ip_knowledge_packs', ['draft_id'], unique=False)
    op.create_index(op.f('ix_ip_knowledge_packs_world_id'), 'ip_knowledge_packs', ['world_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_ip_knowledge_packs_world_id'), table_name='ip_knowledge_packs')
    op.drop_index(op.f('ix_ip_knowledge_packs_draft_id'), table_name='ip_knowledge_packs')
    op.drop_table('ip_knowledge_packs')
