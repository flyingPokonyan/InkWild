import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class Notification(Base):
    """个人通知：一人一行，系统在事件点自动产生。"""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_user_unread", "user_id", "read_at"),
        Index("idx_notifications_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    # signup_grant / review_approved / review_rejected / content_takedown / low_credit
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 结构化数据（draft_id、积分数等），留作日后双语模板重渲染
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Announcement(Base):
    """系统公告：一条一行，admin 创建并发布，发给全体用户。"""

    __tablename__ = "announcements"
    __table_args__ = (Index("idx_announcements_status_pub", "status", "published_at"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(16), default="info")  # info / warning / critical
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft / published
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AnnouncementRead(Base):
    """公告已读 join 表：读了才写一行。"""

    __tablename__ = "announcement_reads"

    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), primary_key=True)
    announcement_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("announcements.id"), primary_key=True
    )
    read_at: Mapped[datetime] = mapped_column(default=utcnow)
