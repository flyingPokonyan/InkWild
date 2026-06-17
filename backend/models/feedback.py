import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class Feedback(Base):
    """用户反馈：bug / 优化建议。用户提交一行，admin 处理并流转状态。"""

    __tablename__ = "feedback"
    __table_args__ = (
        Index("idx_feedback_status_created", "status", "created_at"),
        Index("idx_feedback_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # 允许为空：保留匿名反馈的可能；当前提交要求登录。
    user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(16))  # bug / suggestion
    content: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 截图（OSS）
    page_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 提交时所在页面
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 可选回联方式
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="new")  # new / triaged / resolved
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # 内部备注，仅 admin 可见
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)  # 最近一次对外回复（快照，全量见 events）
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class FeedbackEvent(Base):
    """反馈时间线事件：状态变更 / 管理员回复。一条反馈的处理历史按时间累积，
    供用户在通知里看到「解决的记录」全貌。"""

    __tablename__ = "feedback_events"
    __table_args__ = (Index("idx_feedback_events_fb", "feedback_id", "created_at"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    feedback_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("feedback.id"))
    kind: Mapped[str] = mapped_column(String(16))  # status / reply
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # kind=status 时的新状态
    body: Mapped[str | None] = mapped_column(Text, nullable=True)  # kind=reply 时的回复内容
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
