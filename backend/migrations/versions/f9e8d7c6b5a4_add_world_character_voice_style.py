"""add voice_style to world_characters

Canonical / authored speech style per NPC. IP worlds seed it from the
IPKnowledgePack (voice_style + tone_lingo), original worlds have the generator
produce it. Injected into the NPC system prompt's stable prefix at runtime.
Nullable so legacy rows stay valid and render byte-identical (no voice block).
See docs/superpowers/specs/2026-06-01-npc-voice-style-ip-anchor-design.md

Revision ID: f9e8d7c6b5a4
Revises: f7a3b1c2d4e5
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9e8d7c6b5a4"
down_revision: Union[str, Sequence[str], None] = "f7a3b1c2d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "world_characters",
        sa.Column("voice_style", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("world_characters", "voice_style")
