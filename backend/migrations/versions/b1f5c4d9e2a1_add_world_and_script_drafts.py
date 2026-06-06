"""add world and script drafts

Revision ID: b1f5c4d9e2a1
Revises: 8c4c7c1d2c41
Create Date: 2026-04-08 18:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1f5c4d9e2a1"
down_revision: Union[str, Sequence[str], None] = "8c4c7c1d2c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect_name = bind.dialect.name

    world_columns = {column["name"] for column in inspector.get_columns("worlds")}
    if "locations_data" not in world_columns:
        op.add_column(
            "worlds",
            sa.Column("locations_data", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )
        if dialect_name != "sqlite":
            op.alter_column("worlds", "locations_data", server_default=None)

    table_names = set(inspector.get_table_names())
    if "world_drafts" not in table_names:
        op.create_table(
            "world_drafts",
            sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("world_id", sa.Uuid(as_uuid=False), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("world_id"),
        )

    if "script_drafts" not in table_names:
        op.create_table(
            "script_drafts",
            sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("world_id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("script_id", sa.Uuid(as_uuid=False), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["script_id"], ["scripts.id"]),
            sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("script_id"),
        )

    script_draft_indexes = {index["name"] for index in inspector.get_indexes("script_drafts")} if "script_drafts" in set(sa.inspect(bind).get_table_names()) else set()
    if "idx_script_drafts_world_id" not in script_draft_indexes:
        op.create_index("idx_script_drafts_world_id", "script_drafts", ["world_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_script_drafts_world_id", table_name="script_drafts")
    op.drop_table("script_drafts")
    op.drop_table("world_drafts")
    op.drop_column("worlds", "locations_data")
