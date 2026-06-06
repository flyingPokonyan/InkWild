"""visual_brief and drop poster_image

Revision ID: 58f13b75b16c
Revises: 531ec5f45068
Create Date: 2026-05-10 23:43:07.865243

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '58f13b75b16c'
down_revision: Union[str, Sequence[str], None] = '531ec5f45068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('scripts', sa.Column('visual_brief', sa.JSON(), nullable=True))
    op.add_column('worlds', sa.Column('visual_brief', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.drop_column('worlds', 'poster_image')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('worlds', sa.Column('poster_image', sa.VARCHAR(length=500), server_default=sa.text("''::character varying"), autoincrement=False, nullable=False))
    op.drop_column('worlds', 'visual_brief')
    op.drop_column('scripts', 'visual_brief')
