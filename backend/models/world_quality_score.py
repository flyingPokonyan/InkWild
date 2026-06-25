import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow

_JSONB = JSON().with_variant(JSONB(), "postgresql")


class WorldQualityScore(Base):
    """生成完成后异步打分的结果快照（锁定 done 那一刻，不追草稿后续编辑）。

    plan: docs/plans/2026-06-24-generation-agentic-loop.md
    三类信号一起存：
    - 硬指标（Python，可纵向趋势对比）：角色/可玩/must_have 覆盖/事件数/结构
    - 软分（LLM，仅单次参考，不进趋势）：IP 一致性 / 撞车 / 张力
    - 安全网触发量（盲点补充）：backfill 补了几个主角、prune 删了几个、soft_warning 数
      —— must_have backfill 在 done 前补齐主角，故"最终 must_have 覆盖"永远满分，
         单看会漏判；触发量告诉你"这个分是不是靠补救撑的"。
    常用筛选/排序字段提为标量列，完整明细放 detail JSON。
    """

    __tablename__ = "world_quality_scores"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("generation_tasks.id"), index=True)
    draft_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="world")

    # ---- 硬指标（Python，0 成本，可纵向趋势对比）----
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    playable_count: Mapped[int] = mapped_column(Integer, default=0)
    must_have_total: Mapped[int] = mapped_column(Integer, default=0)
    must_have_covered: Mapped[int] = mapped_column(Integer, default=0)
    events_count: Mapped[int] = mapped_column(Integer, default=0)
    shared_events_count: Mapped[int] = mapped_column(Integer, default=0)
    structure_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-1，结构完整度

    # ---- 软分（LLM，0-10，nullable=软分未跑/失败；仅单次参考，不进趋势）----
    soft_ip_consistency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soft_collision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soft_tension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soft_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- 安全网触发量（盲点补充）----
    backfill_count: Mapped[int] = mapped_column(Integer, default=0)  # critic 阶段补回的 must_have 数
    prune_count: Mapped[int] = mapped_column(Integer, default=0)     # roster 删除的非 canon 数
    soft_warning_count: Mapped[int] = mapped_column(Integer, default=0)

    # ---- 综合（硬指标加权，0-100；软分不参与，避免被宽松软分拉高）----
    overall_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    # ---- 软评门控（P0 两数门控，替代旧 cap-to-55）----
    # blocking_flags: 软裁判触底的维度（如 ["ip_consistency=4","collision=3"]），空=无硬伤。
    # shippable: 无 blocking_flags 即 True。**仅建议、不硬卡发布**，admin 旁路显示红旗。
    blocking_flags: Mapped[list | None] = mapped_column(_JSONB, nullable=True, default=None)
    shippable: Mapped[bool] = mapped_column(default=True, index=True)

    detail: Mapped[dict | None] = mapped_column(_JSONB, nullable=True, default=None)

    scored_at: Mapped[datetime] = mapped_column(default=utcnow)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
