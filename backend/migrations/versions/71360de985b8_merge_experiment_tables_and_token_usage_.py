"""merge experiment_tables and token_usage_outcome

Revision ID: 71360de985b8
Revises: b8c9d0e1f2a3, b8e2c9d4f0a1
Create Date: 2026-05-23 11:14:30.100149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '71360de985b8'
down_revision: Union[str, Sequence[str], None] = ('b8c9d0e1f2a3', 'b8e2c9d4f0a1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
