import uuid
from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow

# 单例行主键：全站只有一行系统配置。
SYSTEM_CONFIG_ID = "singleton"


class SystemConfig(Base):
    """全站级配置（单例行）。第一块 admin 可编辑的全局配置基建，

    后续站点级开关（注册放量、各种 feature flag）都挂这里。
    """

    __tablename__ = "system_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=SYSTEM_CONFIG_ID)

    # 注册放量：open=不限 / capped=按批次名额 / closed=暂停注册
    signup_mode: Mapped[str] = mapped_column(String(16), default="open")
    # 本批名额（capped 时生效）
    signup_cap: Mapped[int] = mapped_column(Integer, default=0)
    # 本批计数起点：统计此刻之后新建的账号数；admin「开新一批」时重置为 now
    signup_batch_start: Mapped[datetime | None] = mapped_column(nullable=True)

    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
