import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

_JSONB = JSON().with_variant(JSONB(), "postgresql")

from database import Base
from utils import utcnow


class GenerationTask(Base):
    __tablename__ = "generation_tasks"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind: Mapped[str] = mapped_column(String(20))
    draft_type: Mapped[str] = mapped_column(String(20))
    draft_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    current_phase: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_event_seq: Mapped[int] = mapped_column(Integer, default=0)
    intermediate_state: Mapped[dict | None] = mapped_column(_JSONB, nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class GenerationTaskEvent(Base):
    __tablename__ = "generation_task_events"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("generation_tasks.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    event_name: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
