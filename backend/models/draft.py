import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow

# Review state lives on the draft (not on the World/Script row) so a published
# work can stay live while a revision is under review. See
# docs/superpowers/specs/2026-05-30-publish-lifecycle-design.md §4.2.
#   editing    — default; unsubmitted (fresh or has pending changes)
#   submitted  — under admin review
#   rejected   — admin rejected (review_note carries the reason)


class WorldDraft(Base):
    __tablename__ = "world_drafts"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"), nullable=True, unique=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    payload_revision: Mapped[int] = mapped_column(Integer, default=0)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    quality_status: Mapped[str] = mapped_column(String(20), default="not_requested", index=True)
    created_by_user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    review_status: Mapped[str] = mapped_column(String(16), default="editing", index=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ScriptDraft(Base):
    __tablename__ = "script_drafts"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"))
    script_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("scripts.id"), nullable=True, unique=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    review_status: Mapped[str] = mapped_column(String(16), default="editing", index=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
