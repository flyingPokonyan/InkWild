"""add memory_entries.embedding column for semantic recall

Phase 1.B.2 — adds a nullable JSON column to store embedding vectors. JSON
keeps the schema portable between PostgreSQL and the SQLite test backend; if
we later switch to native pgvector the data type can be migrated in place.

Revision ID: 3b8d9e1c2f04
Revises: 2a7c9d4e1f03
Create Date: 2026-05-06 19:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3b8d9e1c2f04"
down_revision: Union[str, Sequence[str], None] = "2a7c9d4e1f03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("memory_entries")}
    if "embedding" not in columns:
        op.add_column(
            "memory_entries",
            sa.Column("embedding", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("memory_entries")}
    if "embedding" in columns:
        op.drop_column("memory_entries", "embedding")
