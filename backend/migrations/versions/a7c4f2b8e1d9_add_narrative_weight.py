"""add narrative_weight to world_characters

Revision ID: a7c4f2b8e1d9
Revises: 9a8b7c6d5e4f
Create Date: 2026-05-19 15:00:00.000000

Adds ``world_characters.narrative_weight`` (SmallInteger, default 0). The world
detail page (/api/worlds/{id}) sorts characters by this column so the
protagonist surfaces first. Publish derives the value from the v2 roster
planner signals (``role_tag`` / ``is_image_target``):

- "主角" → 100
- "宿敌" / "反派" → 90
- ``is_image_target=True`` (likely playable) → 70
- otherwise → 50

Existing rows get 0 (server_default); they'll sort last under the new ORDER BY
but stay valid. Admin editor will surface a 0-100 slider later for manual
override.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7c4f2b8e1d9"
down_revision: Union[str, Sequence[str], None] = "9a8b7c6d5e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "world_characters",
        sa.Column(
            "narrative_weight",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("world_characters", "narrative_weight")
