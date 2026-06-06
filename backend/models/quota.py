import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class UserCreationQuota(Base):
    __tablename__ = "user_creation_quotas"
    __table_args__ = (
        UniqueConstraint("user_id", "quota_date", name="uq_user_quota_per_day"),
        Index("idx_user_quota_user_date", "user_id", "quota_date"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    quota_date: Mapped[date] = mapped_column(Date)
    world_generations: Mapped[int] = mapped_column(Integer, default=0)
    script_generations: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
