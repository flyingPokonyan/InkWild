"""add avatar and cover_image fields

Revision ID: d3a1b2c4e5f6
Revises: b1f5c4d9e2a1
Create Date: 2026-04-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3a1b2c4e5f6"
down_revision: Union[str, None] = "a21226f5c969"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("world_characters", sa.Column("avatar", sa.String(500), nullable=True))
    op.add_column("scripts", sa.Column("cover_image", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("scripts", "cover_image")
    op.drop_column("world_characters", "avatar")
