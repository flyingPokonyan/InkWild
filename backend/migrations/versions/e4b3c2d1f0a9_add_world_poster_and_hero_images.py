"""add world poster and hero images

Revision ID: e4b3c2d1f0a9
Revises: d3a1b2c4e5f6
Create Date: 2026-04-10 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e4b3c2d1f0a9"
down_revision: Union[str, Sequence[str], None] = "d3a1b2c4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("worlds", sa.Column("poster_image", sa.String(length=500), nullable=False, server_default=""))
    op.add_column("worlds", sa.Column("hero_image", sa.String(length=500), nullable=False, server_default=""))
    op.execute(
        """
        UPDATE worlds
        SET
            poster_image = COALESCE(NULLIF(cover_image, ''), poster_image),
            hero_image = COALESCE(NULLIF(cover_image, ''), hero_image)
        """
    )


def downgrade() -> None:
    op.drop_column("worlds", "hero_image")
    op.drop_column("worlds", "poster_image")
