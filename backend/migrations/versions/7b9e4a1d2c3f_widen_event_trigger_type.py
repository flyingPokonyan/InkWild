"""widen event trigger type

Revision ID: 7b9e4a1d2c3f
Revises: c6f6a2f4f8d1
Create Date: 2026-04-08 21:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b9e4a1d2c3f"
down_revision: Union[str, Sequence[str], None] = "c6f6a2f4f8d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.alter_column(
            "trigger_type",
            existing_type=sa.String(length=20),
            type_=sa.String(length=50),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.alter_column(
            "trigger_type",
            existing_type=sa.String(length=50),
            type_=sa.String(length=20),
            existing_nullable=False,
        )
