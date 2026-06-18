"""add scripts.local_characters

Script-attached NPCs (反哺产物): characters a script needs that the parent
world roster lacks. Owned by the script; the world is never mutated. Runtime
unions them with world characters at session start.

Revision ID: d4e1f2a3b5c6
Revises: c3f7a0d12e8b
Create Date: 2026-06-18 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e1f2a3b5c6"
down_revision: Union[str, Sequence[str], None] = "c3f7a0d12e8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scripts",
        sa.Column(
            "local_characters",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("scripts", "local_characters")
