"""Phase 1.B.X — NPC reflection (long-term character memory).

Persisted "first-person inner monologue" summary per NPC per session, refreshed
when the NPC accumulates enough new structured memories. Loaded into the NPC
agent's stable system prompt so the NPC has a sense of the whole arc instead
of only the latest few entries.
"""
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class NPCReflection(Base):
    __tablename__ = "npc_reflections"
    __table_args__ = (
        UniqueConstraint("session_id", "npc_name", name="uq_npc_reflections_session_npc"),
        Index("idx_npc_reflections_session", "session_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("game_sessions.id"))
    npc_name: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(Text)
    # Highest memory_entries.id covered by this reflection. Used to count "new
    # memories since last reflect" for the threshold trigger.
    last_memory_id: Mapped[int] = mapped_column(Integer, default=0)
    # How many times this NPC has been reflected on (for telemetry / debug).
    reflection_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)
