import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow

_JSONB = JSON().with_variant(JSONB(), "postgresql")


class GenerationTask(Base):
    __tablename__ = "generation_tasks"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    generation_run_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True, index=True)
    root_task_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True, index=True)
    parent_task_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("generation_tasks.id"), nullable=True, index=True
    )
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
    world_spec: Mapped[dict | None] = mapped_column(_JSONB, nullable=True, default=None)
    world_spec_version: Mapped[int] = mapped_column(Integer, default=0)
    payload_revision: Mapped[int] = mapped_column(Integer, default=0)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
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


class GenerationNodeRun(Base):
    __tablename__ = "generation_node_runs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    generation_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("generation_tasks.id"), index=True)
    node_id: Mapped[str] = mapped_column(String(80), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    spec_version: Mapped[int] = mapped_column(Integer, default=1)
    estimated_calls: Mapped[int] = mapped_column(Integer, default=0)
    actual_calls: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class GenerationAction(Base):
    __tablename__ = "generation_actions"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    generation_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("generation_tasks.id"), index=True)
    node_run_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("generation_node_runs.id"), nullable=True, index=True
    )
    action_type: Mapped[str] = mapped_column(String(20), index=True)
    target_node: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(_JSONB, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class GenerationViolation(Base):
    __tablename__ = "generation_violations"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    generation_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("generation_tasks.id"), index=True)
    node_run_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("generation_node_runs.id"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    path: Mapped[str | None] = mapped_column(String(191), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    repairable: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_by_action_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("generation_actions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
