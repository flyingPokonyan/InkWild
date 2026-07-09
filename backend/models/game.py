import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class GameSession(Base):
    __tablename__ = "game_sessions"
    __table_args__ = (
        Index("idx_game_sessions_user_status", "user_id", "status"),
        Index("idx_game_sessions_user_last_played", "user_id", "last_played_at"),
        Index("idx_game_sessions_world_id", "world_id"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    world_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"))
    character_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("world_characters.id"))
    script_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("scripts.id"), nullable=True)
    authors_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_action_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="playing")
    game_state: Mapped[dict] = mapped_column(JSON, default=dict)
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ending_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rounds_played: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_played_at: Mapped[datetime] = mapped_column(default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_messages_session_created", "session_id", "created_at"),
        Index("idx_messages_session_compressed", "session_id", "is_compressed"),
        Index("idx_messages_session_role", "session_id", "role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("game_sessions.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    state_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Phase 1.B.4 — per-NPC raw dialogue for voice-anchor recall.
    # Stored as {npc_name: dialogue_text}. Populated only on assistant
    # messages that include NPC interactions; NULL for user messages and
    # turns with no NPC speech.
    npc_dialogues: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class TokenUsage(Base):
    __tablename__ = "token_usage"
    __table_args__ = (
        Index("idx_token_usage_session", "session_id"),
        Index("idx_token_usage_task_id", "task_id"),
        Index("idx_token_usage_created", "created_at"),
        CheckConstraint(
            "session_id IS NOT NULL OR task_id IS NOT NULL",
            name="ck_token_usage_session_or_task",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # One of session_id / task_id must be non-null (see CHECK above).
    # session_id: game turns; task_id: workshop generation tasks; both
    # populated only when the row's purpose dictates.
    session_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("game_sessions.id"), nullable=True
    )
    task_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("generation_tasks.id"), nullable=True
    )
    # Coarse-grained surface label. CHECK on column intentionally skipped —
    # enforced at the sink layer so adding a new bucket doesn't need a
    # migration. Current buckets: game / moderation / reflection /
    # compression / world_gen / script_gen / image_gen.
    purpose: Mapped[str] = mapped_column(String(20))
    # Free-form sub-stage for drill-down (e.g. "world_gen.research").
    phase: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(50))
    provider_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    # Prefix-cache observability (DeepSeek-style). NULL = provider didn't
    # report cache stats (unsupported); 0 = reported but no hit. Kept
    # distinct so analytics can tell "no cache" from "cache cold". cost_cents
    # is NOT yet cache-aware — re-rating cache-hit tokens at the discounted
    # price is a deliberate follow-up gated on observing real hit rates.
    cache_hit_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_miss_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Image-call rows put per-call count here; text rows stay at 0.
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    # Phase 9 (2026-05) — Director outcome observability. Lets admin dashboards
    # compute per-model parse-failure rate so model swaps don't silently
    # degrade gameplay. Values:
    #   "success"          — got a usable result on the first attempt
    #   "retried_success"  — succeeded after one or more retries
    #   "parse_failure"    — gave up after all retries (raises DirectorParseError)
    #   "error"            — non-parse failure (timeout, provider exception, etc.)
    # Default "success" matches the historical row shape so existing analytics
    # queries that ignore this column keep working.
    outcome: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
