"""add auth_identities verified_at

Revision ID: 757e92842328
Revises: f9e8d7c6b5a4
Create Date: 2026-06-02 05:24:49.694843

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '757e92842328'
down_revision: Union[str, Sequence[str], None] = 'f9e8d7c6b5a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("auth_identities", sa.Column("verified_at", sa.DateTime(), nullable=True))
    # Backfill: existing identities (seed/dev/already-registered users) are trusted as
    # verified, so the new login gate does not lock them out after this migration.
    op.execute("UPDATE auth_identities SET verified_at = created_at WHERE verified_at IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("auth_identities", "verified_at")
