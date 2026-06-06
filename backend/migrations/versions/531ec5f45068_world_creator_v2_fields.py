"""world_creator_v2_fields

Revision ID: 531ec5f45068
Revises: f5a2b3c4d6e7
Create Date: 2026-05-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "531ec5f45068"
down_revision: Union[str, Sequence[str], None] = "9b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("worlds", sa.Column("lore_pack", JSONB, nullable=True))
    op.add_column("worlds", sa.Column("shared_events", JSONB, nullable=True))
    op.add_column("worlds", sa.Column("events_data", JSONB, nullable=True))
    op.add_column("generation_tasks", sa.Column("intermediate_state", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("generation_tasks", "intermediate_state")
    op.drop_column("worlds", "events_data")
    op.drop_column("worlds", "shared_events")
    op.drop_column("worlds", "lore_pack")
