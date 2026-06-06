"""cover_brief redesign — add gender + ending cover_image, drop visual_brief

Revision ID: 9a8b7c6d5e4f
Revises: e2f3a4b5c6d7
Create Date: 2026-05-19 12:00:00.000000

Schema changes for the 2026-05 封面图生成 重构 (see
``docs/plans/cover-image-prompt-redesign-2026-05.md``):

- ``world_characters.gender`` (NEW) — "男" / "女" / "" (default empty);
  drives the 4-dim portrait descriptor for original-world characters.
  IP-pack characters fall through to reference_anchor and may leave this
  blank.
- ``endings.cover_image`` (NEW, nullable) — 3:2 ending card image URL;
  NULL means generation failed or hasn't run yet; front-end falls back to
  text-only ending display.
- ``worlds.visual_brief`` (DROPPED) — the old WorldVisualBrief JSONB is
  no longer persisted; new pipeline derives CoverBrief on-the-fly each
  generation run.
- ``scripts.visual_brief`` (DROPPED) — same.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9a8b7c6d5e4f"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. world_characters.gender — NEW with empty-string default so existing
    #    rows are valid without backfill. Admin can fill later in the editor.
    op.add_column(
        "world_characters",
        sa.Column("gender", sa.String(length=10), nullable=False, server_default=""),
    )
    # 2. endings.cover_image — NEW, nullable (NULL = no card image; front-end
    #    fall back to text-only ending screen).
    op.add_column(
        "endings",
        sa.Column("cover_image", sa.String(length=500), nullable=True),
    )
    # 3. Drop worlds.visual_brief — new pipeline does not persist briefs.
    op.drop_column("worlds", "visual_brief")
    # 4. Drop scripts.visual_brief — same.
    op.drop_column("scripts", "visual_brief")


def downgrade() -> None:
    """Downgrade schema — restore visual_brief columns and drop new ones.

    Note: dropped JSONB content is NOT recoverable; downgrade restores the
    column shape but rows will all have NULL.
    """
    op.add_column(
        "scripts",
        sa.Column("visual_brief", sa.JSON(), nullable=True),
    )
    op.add_column(
        "worlds",
        sa.Column(
            "visual_brief",
            sa.JSON().with_variant(
                sa.dialects.postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=True,
        ),
    )
    op.drop_column("endings", "cover_image")
    op.drop_column("world_characters", "gender")
