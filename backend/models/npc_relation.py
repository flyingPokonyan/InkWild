"""NPC-2 — persistent NPC↔NPC relations within a single session.

Directed (A→B and B→A are separate rows; trust may be asymmetric — A暗恋B
while B doesn't know). Seeded at session start from
``WorldCharacter.initial_peer_relations``. NPC-2 is read-only: NPC-3 (background
simulation) will own the dynamic mutation path later.
"""
from datetime import datetime

from sqlalchemy import ForeignKey, Index, SmallInteger, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class NPCRelation(Base):
    __tablename__ = "npc_relations"
    __table_args__ = (
        UniqueConstraint("session_id", "npc_a", "npc_b", name="uq_npc_relations_session_pair"),
        Index("idx_npc_relations_session_a", "session_id", "npc_a"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("game_sessions.id"))
    # Subject ("A's view of B"). Reverse direction lives in a separate row.
    npc_a: Mapped[str] = mapped_column(String(50))
    npc_b: Mapped[str] = mapped_column(String(50))
    # Hard-clamped to [-10, 10] at write time; default neutral.
    trust: Mapped[int] = mapped_column(SmallInteger, default=0)
    relationship_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    history_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Round of the most recent A↔B interaction. NPC-3 will bump this when
    # background events fire; for NPC-2 it stays at 0 after seed.
    last_event_round: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)
