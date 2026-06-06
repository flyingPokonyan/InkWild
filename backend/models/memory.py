from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, SmallInteger, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    __table_args__ = (
        Index("idx_memory_session", "session_id"),
        Index("idx_memory_session_type", "session_id", "memory_type"),
        Index("idx_memory_npc", "session_id", "related_npc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("game_sessions.id"))
    memory_type: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    round_number: Mapped[int] = mapped_column(Integer)
    importance: Mapped[int] = mapped_column(SmallInteger, default=5)
    related_npc: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Phase 1.B.2 — embedding for semantic recall. Stored as JSON list of
    # floats so the same schema works on PostgreSQL and SQLite (tests). NULL
    # when embedding is disabled or the embedding API failed at write time.
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
