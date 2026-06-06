"""add review_status / review_note to world_drafts and script_drafts

Review state lives on the draft (not the World/Script row) so a published work
can stay live while a revision is under review. See
docs/superpowers/specs/2026-05-30-publish-lifecycle-design.md §4.2.

Revision ID: f7a3b1c2d4e5
Revises: 28b09d34bc01
Create Date: 2026-05-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7a3b1c2d4e5"
down_revision: Union[str, Sequence[str], None] = "28b09d34bc01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("world_drafts", "script_drafts"):
        op.add_column(
            table,
            sa.Column(
                "review_status",
                sa.String(length=16),
                nullable=False,
                server_default="editing",
            ),
        )
        # match the model (Python-side default); existing rows already backfilled
        op.alter_column(table, "review_status", server_default=None)
        op.add_column(table, sa.Column("review_note", sa.Text(), nullable=True))
        op.create_index(
            f"ix_{table}_review_status", table, ["review_status"], unique=False
        )


def downgrade() -> None:
    for table in ("world_drafts", "script_drafts"):
        op.drop_index(f"ix_{table}_review_status", table_name=table)
        op.drop_column(table, "review_note")
        op.drop_column(table, "review_status")
