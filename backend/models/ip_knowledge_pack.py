import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow

_JSONB = JSON().with_variant(JSONB(), "postgresql")


class IPKnowledgePack(Base):
    """High-fidelity IP knowledge pack — extracted IP canon for a world or draft.

    `world_id` and `draft_id` are mutually exclusive: an IP pack belongs to either
    a published world OR a draft (not both). Application logic is responsible for
    enforcing this invariant.
    """

    __tablename__ = "ip_knowledge_packs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"), nullable=True, index=True)
    draft_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("world_drafts.id"), nullable=True, index=True)
    ip_name: Mapped[str] = mapped_column(String(200))
    fidelity_mode: Mapped[str] = mapped_column(String(20))
    pack_json: Mapped[dict] = mapped_column(_JSONB)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
