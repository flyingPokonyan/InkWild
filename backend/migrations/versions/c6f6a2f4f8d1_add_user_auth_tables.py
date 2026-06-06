"""add user auth tables

Revision ID: c6f6a2f4f8d1
Revises: b1f5c4d9e2a1
Create Date: 2026-04-08 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c6f6a2f4f8d1"
down_revision: Union[str, Sequence[str], None] = "b1f5c4d9e2a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_users_table() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("nickname", sa.String(length=50), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_auth_identities_table() -> None:
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.String(length=191), nullable=False),
        sa.Column("credential_hash", sa.Text(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("union_id", sa.String(length=191), nullable=True),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_auth_identity_provider_user"),
    )
    op.create_index("idx_auth_identities_user", "auth_identities", ["user_id"], unique=False)
    op.create_index("idx_auth_identities_union", "auth_identities", ["union_id"], unique=False)


def _create_web_sessions_table() -> None:
    op.create_table(
        "web_sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_web_sessions_user", "web_sessions", ["user_id"], unique=False)
    op.create_index("idx_web_sessions_expires", "web_sessions", ["expires_at"], unique=False)


def _drop_table_if_exists(inspector: sa.Inspector, table_name: str) -> None:
    if table_name not in set(inspector.get_table_names()):
        return

    for index in inspector.get_indexes(table_name):
        op.drop_index(index["name"], table_name=table_name)
    op.drop_table(table_name)


def _recreate_game_tables() -> None:
    # Anonymous game data can be discarded in this round. Recreate the ownership-sensitive
    # tables instead of inventing a player_id -> user_id backfill.
    op.create_table(
        "game_sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("world_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("character_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("script_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("authors_note", sa.Text(), nullable=True),
        sa.Column("state_snapshot", sa.JSON(), nullable=True),
        sa.Column("last_action_text", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("game_state", sa.JSON(), nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("ending_type", sa.String(length=50), nullable=True),
        sa.Column("rounds_played", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_played_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["script_id"], ["scripts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_game_sessions_user_status", "game_sessions", ["user_id", "status"], unique=False)
    op.create_index("idx_game_sessions_user_last_played", "game_sessions", ["user_id", "last_played_at"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("state_snapshot", sa.JSON(), nullable=True),
        sa.Column("is_compressed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_messages_session_compressed", "messages", ["session_id", "is_compressed"], unique=False)
    op.create_index("idx_messages_session_created", "messages", ["session_id", "created_at"], unique=False)

    op.create_table(
        "token_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=50), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_token_usage_created", "token_usage", ["created_at"], unique=False)
    op.create_index("idx_token_usage_session", "token_usage", ["session_id"], unique=False)

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("memory_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("importance", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_memory_session", "memory_entries", ["session_id"], unique=False)
    op.create_index("idx_memory_session_type", "memory_entries", ["session_id", "memory_type"], unique=False)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "users" not in existing_tables:
        _create_users_table()
    if "auth_identities" not in existing_tables:
        _create_auth_identities_table()
    if "web_sessions" not in existing_tables:
        _create_web_sessions_table()

    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    game_columns = {column["name"] for column in inspector.get_columns("game_sessions")} if "game_sessions" in existing_tables else set()
    if "game_sessions" not in existing_tables or "player_id" in game_columns or "user_id" not in game_columns:
        _drop_table_if_exists(inspector, "memory_entries")
        inspector = sa.inspect(bind)
        _drop_table_if_exists(inspector, "token_usage")
        inspector = sa.inspect(bind)
        _drop_table_if_exists(inspector, "messages")
        inspector = sa.inspect(bind)
        _drop_table_if_exists(inspector, "game_sessions")
        _recreate_game_tables()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _drop_table_if_exists(inspector, "memory_entries")
    inspector = sa.inspect(bind)
    _drop_table_if_exists(inspector, "token_usage")
    inspector = sa.inspect(bind)
    _drop_table_if_exists(inspector, "messages")
    inspector = sa.inspect(bind)
    _drop_table_if_exists(inspector, "game_sessions")

    op.create_table(
        "game_sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("world_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("character_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("script_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("authors_note", sa.Text(), nullable=True),
        sa.Column("state_snapshot", sa.JSON(), nullable=True),
        sa.Column("last_action_text", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("game_state", sa.JSON(), nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("ending_type", sa.String(length=50), nullable=True),
        sa.Column("rounds_played", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_played_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["script_id"], ["scripts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_game_sessions_player_status", "game_sessions", ["player_id", "status"], unique=False)
    op.create_index("idx_game_sessions_player_last_played", "game_sessions", ["player_id", "last_played_at"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("state_snapshot", sa.JSON(), nullable=True),
        sa.Column("is_compressed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_messages_session_compressed", "messages", ["session_id", "is_compressed"], unique=False)
    op.create_index("idx_messages_session_created", "messages", ["session_id", "created_at"], unique=False)

    op.create_table(
        "token_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=50), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_token_usage_created", "token_usage", ["created_at"], unique=False)
    op.create_index("idx_token_usage_session", "token_usage", ["session_id"], unique=False)

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("memory_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("importance", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_memory_session", "memory_entries", ["session_id"], unique=False)
    op.create_index("idx_memory_session_type", "memory_entries", ["session_id", "memory_type"], unique=False)

    inspector = sa.inspect(bind)
    _drop_table_if_exists(inspector, "web_sessions")
    inspector = sa.inspect(bind)
    _drop_table_if_exists(inspector, "auth_identities")
    inspector = sa.inspect(bind)
    _drop_table_if_exists(inspector, "users")
