"""add pricing to provider_models

Revision ID: a1b2c3d4e5f6
Revises: 12d373a9cd9e
Create Date: 2026-05-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "12d373a9cd9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("provider_models", sa.Column("input_price_cents_per_million_tokens", sa.Integer(), nullable=True))
    op.add_column("provider_models", sa.Column("output_price_cents_per_million_tokens", sa.Integer(), nullable=True))
    op.add_column("provider_models", sa.Column("image_price_cents_per_image", sa.Integer(), nullable=True))
    op.add_column("provider_models", sa.Column("price_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("provider_models", "price_updated_at")
    op.drop_column("provider_models", "image_price_cents_per_image")
    op.drop_column("provider_models", "output_price_cents_per_million_tokens")
    op.drop_column("provider_models", "input_price_cents_per_million_tokens")
