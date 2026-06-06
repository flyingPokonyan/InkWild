import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, JSON, SmallInteger, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(SmallInteger, default=3)
    estimated_time: Mapped[str] = mapped_column(String(50), default="30-60 min")
    events_data: Mapped[list[dict]] = mapped_column(JSON, default=lambda _ctx=None: [])
    clues_data: Mapped[dict] = mapped_column(JSON, default=dict)
    endings_data: Mapped[list[dict]] = mapped_column(JSON, default=lambda _ctx=None: [])
    script_setting: Mapped[str] = mapped_column(Text, default="")
    playable_character_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    script_type: Mapped[str] = mapped_column(String(30), default="mystery")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="private", index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
