"""token usage AOP fields

Revision ID: e2f3a4b5c6d7
Revises: be8e4a08d270
Create Date: 2026-05-18 00:00:00.000000

Make ``token_usage`` capable of recording LLM cost across all surfaces
(game turns, world / script generation tasks, image generation) — not
just game sessions. See ``docs/plans/token-usage-aop-2026-05.md``.

Changes:

* ``session_id`` → nullable (workshop & image-gen rows have no session)
* new ``task_id`` (nullable FK → generation_tasks.id) for workshop rows
* new ``purpose`` varchar(20) NOT NULL — labels each row's surface:
  ``game`` / ``moderation`` / ``reflection`` / ``compression`` /
  ``world_gen`` / ``script_gen`` / ``image_gen``
* new ``phase`` varchar(50) nullable — free-form sub-stage tag for
  drill-down (e.g. ``world_gen.research``)
* new ``image_count`` integer NOT NULL default 0 — image rows put the
  per-call image count here; text rows stay at 0
* CHECK ``session_id IS NOT NULL OR task_id IS NOT NULL``

Legacy rows are backfilled to ``purpose='game'`` before NOT NULL is
applied.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "be8e4a08d270"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _existing_columns("token_usage")

    # --- new columns (add as nullable first, backfill, then tighten) ---
    if "task_id" not in columns:
        op.add_column(
            "token_usage",
            sa.Column("task_id", sa.Uuid(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "fk_token_usage_task_id",
            "token_usage",
            "generation_tasks",
            ["task_id"],
            ["id"],
        )
        op.create_index(
            "idx_token_usage_task_id",
            "token_usage",
            ["task_id"],
        )

    if "purpose" not in columns:
        op.add_column(
            "token_usage",
            sa.Column("purpose", sa.String(length=20), nullable=True),
        )

    if "phase" not in columns:
        op.add_column(
            "token_usage",
            sa.Column("phase", sa.String(length=50), nullable=True),
        )

    if "image_count" not in columns:
        op.add_column(
            "token_usage",
            sa.Column(
                "image_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    # --- backfill legacy rows: everything that exists today is a game turn ---
    op.execute("UPDATE token_usage SET purpose = 'game' WHERE purpose IS NULL")

    # --- tighten purpose to NOT NULL ---
    op.alter_column("token_usage", "purpose", nullable=False)

    # --- relax session_id ---
    op.alter_column("token_usage", "session_id", nullable=True)

    # --- at-least-one constraint ---
    op.create_check_constraint(
        "ck_token_usage_session_or_task",
        "token_usage",
        "session_id IS NOT NULL OR task_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_token_usage_session_or_task",
        "token_usage",
        type_="check",
    )
    op.alter_column("token_usage", "session_id", nullable=False)

    columns = _existing_columns("token_usage")
    if "image_count" in columns:
        op.drop_column("token_usage", "image_count")
    if "phase" in columns:
        op.drop_column("token_usage", "phase")
    if "purpose" in columns:
        op.drop_column("token_usage", "purpose")
    if "task_id" in columns:
        op.drop_index("idx_token_usage_task_id", table_name="token_usage")
        op.drop_constraint(
            "fk_token_usage_task_id",
            "token_usage",
            type_="foreignkey",
        )
        op.drop_column("token_usage", "task_id")
