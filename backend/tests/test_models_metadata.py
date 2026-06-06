from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from sqlalchemy import create_engine, inspect

from database import Base
from models import (
    AdminAuditLog,
    CaseBoardHistory,
    Character,
    CreditConfig,
    CreditHold,
    CreditLedger,
    CreditWallet,
    Ending,
    Event,
    GameSession,
    GenerationTask,
    GenerationTaskEvent,
    IPKnowledgePack,
    MemoryEntry,
    Message,
    ModelCapabilityProbe,
    ModelProvider,
    ModelSlotBinding,
    NPC,
    NPCReflection,
    NPCRelation,
    ProviderModel,
    Script,
    ScriptDraft,
    TokenUsage,
    UserCreationQuota,
    World,
    WorldCharacter,
    WorldDraft,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "472da503b7df_add_scripts_table_and_session_fields.py"
)
MIGRATION_SPEC = spec_from_file_location("migration_472da503b7df", MIGRATION_PATH)
assert MIGRATION_SPEC is not None and MIGRATION_SPEC.loader is not None
MIGRATION = module_from_spec(MIGRATION_SPEC)
MIGRATION_SPEC.loader.exec_module(MIGRATION)

AUTH_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "c6f6a2f4f8d1_add_user_auth_tables.py"
)


class FakeInspector:
    def __init__(self, foreign_keys: list[dict]) -> None:
        self._foreign_keys = foreign_keys

    def get_foreign_keys(self, table_name: str) -> list[dict]:
        return self._foreign_keys


def test_all_tables_create_on_sqlite():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())
    assert table_names == {
        "users",
        "auth_identities",
        "web_sessions",
        World.__tablename__,
        NPC.__tablename__,
        Event.__tablename__,
        Character.__tablename__,
        Ending.__tablename__,
        WorldCharacter.__tablename__,
        MemoryEntry.__tablename__,
        "scripts",
        WorldDraft.__tablename__,
        ScriptDraft.__tablename__,
        GameSession.__tablename__,
        Message.__tablename__,
        TokenUsage.__tablename__,
        AdminAuditLog.__tablename__,
        GenerationTask.__tablename__,
        GenerationTaskEvent.__tablename__,
        ModelProvider.__tablename__,
        ProviderModel.__tablename__,
        ModelSlotBinding.__tablename__,
        ModelCapabilityProbe.__tablename__,
        NPCReflection.__tablename__,
        NPCRelation.__tablename__,
        CaseBoardHistory.__tablename__,
        UserCreationQuota.__tablename__,
        IPKnowledgePack.__tablename__,
        CreditWallet.__tablename__,
        CreditLedger.__tablename__,
        CreditConfig.__tablename__,
        CreditHold.__tablename__,
    }


def test_game_sessions_include_phase2_columns():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)

    game_session_columns = {column["name"]: column for column in inspect(engine).get_columns(GameSession.__tablename__)}
    column_names = set(game_session_columns)
    assert {
        "user_id",
        "script_id",
        "authors_note",
        "state_snapshot",
        "last_action_text",
        "retry_count",
        "version",
    }.issubset(column_names)
    assert "player_id" not in column_names
    assert game_session_columns["retry_count"]["nullable"] is False
    assert game_session_columns["version"]["nullable"] is False
    assert game_session_columns["script_id"]["nullable"] is True


def test_users_include_profile_and_session_tracking_columns():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)

    user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
    identity_columns = {column["name"] for column in inspect(engine).get_columns("auth_identities")}
    session_columns = {column["name"] for column in inspect(engine).get_columns("web_sessions")}

    assert {
        "status",
        "nickname",
        "avatar_url",
        "created_at",
        "updated_at",
        "last_login_at",
    }.issubset(user_columns)
    assert {
        "provider",
        "provider_user_id",
        "credential_hash",
        "email",
        "phone",
        "union_id",
        "profile",
        "created_at",
        "last_login_at",
    }.issubset(identity_columns)
    assert {
        "user_id",
        "expires_at",
        "created_at",
        "last_seen_at",
        "user_agent",
        "ip_address",
    }.issubset(session_columns)


def test_script_json_defaults_are_list_shaped():
    assert Script.__table__.c.events_data.default.arg(None) == []
    assert Script.__table__.c.endings_data.default.arg(None) == []


def test_migration_detects_unnamed_script_foreign_key():
    inspector = FakeInspector(
        [
            {
                "name": None,
                "constrained_columns": ["script_id"],
                "referred_table": "scripts",
                "referred_columns": ["id"],
            }
        ]
    )

    assert MIGRATION._has_matching_foreign_key(
        inspector,
        "game_sessions",
        ["script_id"],
        "scripts",
        ["id"],
    )


def test_user_auth_migration_exists_with_expected_revision_chain():
    assert AUTH_MIGRATION_PATH.exists()

    migration_spec = spec_from_file_location("migration_c6f6a2f4f8d1", AUTH_MIGRATION_PATH)
    assert migration_spec is not None and migration_spec.loader is not None

    migration = module_from_spec(migration_spec)
    migration_spec.loader.exec_module(migration)

    assert migration.revision == "c6f6a2f4f8d1"
    assert migration.down_revision == "b1f5c4d9e2a1"
