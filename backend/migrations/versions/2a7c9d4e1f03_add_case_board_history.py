"""add case board history

Revision ID: 2a7c9d4e1f03
Revises: 1b6c7d8e9f0a
Create Date: 2026-04-30 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2a7c9d4e1f03"
down_revision: Union[str, Sequence[str], None] = "1b6c7d8e9f0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "case_board_history" not in table_names:
        op.create_table(
            "case_board_history",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("round_number", sa.Integer(), nullable=False),
            sa.Column("op_type", sa.String(length=50), nullable=False),
            sa.Column("path", sa.JSON(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("before", sa.JSON(), nullable=True),
            sa.Column("after", sa.JSON(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    index_names = {index["name"] for index in inspector.get_indexes("case_board_history")}
    if "idx_case_board_history_session_id" not in index_names:
        op.create_index(
            "idx_case_board_history_session_id",
            "case_board_history",
            ["session_id"],
            unique=False,
        )
    if "idx_case_board_history_session_id_id" not in index_names:
        op.create_index(
            "idx_case_board_history_session_id_id",
            "case_board_history",
            ["session_id", "id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "case_board_history" not in table_names:
        return

    index_names = {index["name"] for index in inspector.get_indexes("case_board_history")}
    if "idx_case_board_history_session_id_id" in index_names:
        op.drop_index("idx_case_board_history_session_id_id", table_name="case_board_history")
    if "idx_case_board_history_session_id" in index_names:
        op.drop_index("idx_case_board_history_session_id", table_name="case_board_history")
    op.drop_table("case_board_history")
