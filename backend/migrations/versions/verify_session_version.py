"""verify session version

Revision ID: 1b6c7d8e9f0a
Revises: 0a5b6c7d8e9f
Create Date: 2026-04-30 16:05:00.000000

Run directly from backend/:
    python migrations/versions/verify_session_version.py
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
revision: str = "1b6c7d8e9f0a"
down_revision: Union[str, Sequence[str], None] = "0a5b6c7d8e9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import settings  # noqa: E402


def _verify_sync(connection) -> None:
    columns = {column["name"]: column for column in sa.inspect(connection).get_columns("game_sessions")}
    if "version" not in columns:
        raise RuntimeError("game_sessions.version column is missing")
    if columns["version"].get("nullable"):
        raise RuntimeError("game_sessions.version must be NOT NULL")

    null_count = connection.execute(sa.text("SELECT COUNT(*) FROM game_sessions WHERE version IS NULL")).scalar_one()
    if null_count:
        raise RuntimeError(f"game_sessions.version has {null_count} NULL values")


def upgrade() -> None:
    _verify_sync(op.get_bind())


def downgrade() -> None:
    pass


async def verify_session_version(database_url: str | None = None) -> None:
    engine = create_async_engine(database_url or settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_verify_sync)
    finally:
        await engine.dispose()


def main() -> None:
    database_url = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(verify_session_version(database_url))
    print("game_sessions.version verified")


if __name__ == "__main__":
    main()
