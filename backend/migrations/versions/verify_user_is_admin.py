"""verify user is_admin

Revision ID: 7e1a9c0d4b2f
Revises: 4d6f8a1b3c92
Create Date: 2026-04-30 00:10:00.000000

This migration verifies the users.is_admin schema invariant. It can also be
run directly from repo root:
    python backend/migrations/versions/verify_user_is_admin.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


# revision identifiers, used by Alembic.
revision: str = "7e1a9c0d4b2f"
down_revision: Union[str, Sequence[str], None] = "4d6f8a1b3c92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import settings  # noqa: E402


def _verify_sync(connection) -> None:
    columns = {column["name"]: column for column in sa.inspect(connection).get_columns("users")}
    if "is_admin" not in columns:
        raise RuntimeError("users.is_admin column is missing")

    nullable = columns["is_admin"].get("nullable")
    if nullable:
        raise RuntimeError("users.is_admin must be NOT NULL")

    null_count = connection.execute(sa.text("SELECT COUNT(*) FROM users WHERE is_admin IS NULL")).scalar_one()
    if null_count:
        raise RuntimeError(f"users.is_admin has {null_count} NULL values")


def upgrade() -> None:
    _verify_sync(op.get_bind())


def downgrade() -> None:
    pass


async def verify_user_is_admin(database_url: str | None = None) -> None:
    engine = create_async_engine(database_url or settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_verify_sync)
    finally:
        await engine.dispose()


def main() -> None:
    database_url = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(verify_user_is_admin(database_url))
    print("users.is_admin verified")


if __name__ == "__main__":
    main()
