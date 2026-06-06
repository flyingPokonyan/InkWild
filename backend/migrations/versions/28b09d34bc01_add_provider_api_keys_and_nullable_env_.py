"""add provider api_keys and nullable env name

Revision ID: 28b09d34bc01
Revises: e7f8a9b0c1d2
Create Date: 2026-05-30 15:14:38.354078

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28b09d34bc01'
down_revision: Union[str, Sequence[str], None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "model_providers",
        sa.Column("api_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.alter_column("model_providers", "api_keys", server_default=None)
    op.alter_column(
        "model_providers", "api_key_env_name",
        existing_type=sa.String(length=80), nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "model_providers", "api_key_env_name",
        existing_type=sa.String(length=80), nullable=False,
    )
    op.drop_column("model_providers", "api_keys")
