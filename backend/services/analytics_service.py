from datetime import datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.game import GameSession, TokenUsage
from models.generation_task import GenerationTask
from models.model_management import ProviderModel
from models.user import User
from models.world import World
from utils import beijing_date, beijing_day_start_utc, serialize_utc_datetime, utcnow


def _utc_cutoff(days: int) -> datetime:
    """DB 列是 timestamp without time zone，统一用 naive UTC。"""
    return utcnow() - timedelta(days=days)


# ────────────── Session cost summary (existing) ──────────────
async def session_cost_summary(db: AsyncSession, days: int = 7) -> dict:
    cutoff = _utc_cutoff(days)
    rows = (
        await db.execute(
            select(
                GameSession.id,
                func.coalesce(func.sum(TokenUsage.cost_cents), 0).label("cost"),
            )
            .join(TokenUsage, TokenUsage.session_id == GameSession.id, isouter=True)
            .where(GameSession.started_at >= cutoff)
            .group_by(GameSession.id)
        )
    ).all()
    costs = sorted(r.cost for r in rows)
    n = len(costs)
    total = sum(costs)
    return {
        "window_days": days,
        "total_sessions": n,
        "total_cost_cents": total,
        "avg_cost_cents": total // n if n else 0,
        "p50_cost_cents": costs[n // 2] if n else 0,
        "p90_cost_cents": costs[min(int(n * 0.9), n - 1)] if n else 0,
        "max_cost_cents": costs[-1] if n else 0,
    }


# ────────────── Generation task summary (existing) ──────────────
async def generation_task_summary(
    db: AsyncSession, days: int = 7, kind: str | None = None
) -> dict:
    cutoff = _utc_cutoff(days)
    stmt = select(GenerationTask).where(GenerationTask.created_at >= cutoff)
    if kind:
        stmt = stmt.where(GenerationTask.kind == kind)
    tasks = (await db.execute(stmt)).scalars().all()
    return {
        "window_days": days,
        "kind": kind,
        "total_tasks": len(tasks),
        "by_status": {
            st: sum(1 for t in tasks if t.status == st)
            for st in ("pending", "running", "succeeded", "failed", "cancelled")
        },
    }


# ────────────── Cost trend (daily bucket) ──────────────
async def cost_trend_daily(db: AsyncSession, days: int = 30) -> dict:
    """按北京时间日切的 cost_cents 序列。"""
    today_start = beijing_day_start_utc()
    cutoff = today_start - timedelta(days=days - 1)
    next_day_start = today_start + timedelta(days=1)
    rows = (
        await db.execute(
            select(TokenUsage.created_at, TokenUsage.cost_cents)
            .where(TokenUsage.created_at >= cutoff, TokenUsage.created_at < next_day_start)
            .order_by(TokenUsage.created_at)
        )
    ).all()
    totals_by_date: dict[str, int] = {}
    for row in rows:
        date = beijing_date(row.created_at)
        totals_by_date[date] = totals_by_date.get(date, 0) + int(row.cost_cents or 0)
    series = [
        {"date": date, "cost_cents": cost}
        for date, cost in sorted(totals_by_date.items())
    ]
    return {
        "window_days": days,
        "series": series,
        "total_cents": sum(r["cost_cents"] for r in series),
    }


# ────────────── Cost by provider ──────────────
async def cost_by_provider(db: AsyncSession, days: int = 30) -> dict:
    cutoff = _utc_cutoff(days)
    # 优先用 provider_name；老行回退到 provider
    name_col = func.coalesce(TokenUsage.provider_name, TokenUsage.provider).label("provider")
    rows = (
        await db.execute(
            select(
                name_col,
                func.coalesce(func.sum(TokenUsage.cost_cents), 0).label("cost"),
                func.count(func.distinct(TokenUsage.session_id)).label("sessions"),
            )
            .where(TokenUsage.created_at >= cutoff)
            .group_by(name_col)
            .order_by(desc("cost"))
        )
    ).all()
    total = sum(r.cost for r in rows)
    items = [
        {
            "provider": r.provider or "unknown",
            "cost_cents": int(r.cost),
            "sessions": int(r.sessions),
            "share": (r.cost / total) if total > 0 else 0,
        }
        for r in rows
    ]
    return {"window_days": days, "items": items, "total_cents": int(total)}


# ────────────── Cost by model ──────────────
async def cost_by_model(db: AsyncSession, days: int = 30) -> dict:
    cutoff = _utc_cutoff(days)
    # 优先 model_id 新列，回退到 model 老列
    model_col = func.coalesce(TokenUsage.model_id, TokenUsage.model).label("model_id")
    provider_col = func.coalesce(TokenUsage.provider_name, TokenUsage.provider).label("provider")
    rows = (
        await db.execute(
            select(
                model_col,
                provider_col,
                func.coalesce(func.sum(TokenUsage.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(TokenUsage.output_tokens), 0).label("output_tokens"),
                func.count().label("calls"),
                func.coalesce(func.sum(TokenUsage.cost_cents), 0).label("cost"),
            )
            .where(TokenUsage.created_at >= cutoff)
            .group_by(model_col, provider_col)
            .order_by(desc("cost"))
        )
    ).all()
    # 关联 provider_models 拿 display_name
    model_ids = [r.model_id for r in rows if r.model_id]
    display_map: dict[str, str] = {}
    if model_ids:
        name_rows = (
            await db.execute(
                select(ProviderModel.model_id, ProviderModel.display_name).where(
                    ProviderModel.model_id.in_(model_ids)
                )
            )
        ).all()
        display_map = {m_id: name for m_id, name in name_rows}

    total = sum(r.cost for r in rows)
    items = [
        {
            "model_id": r.model_id or "unknown",
            "display_name": display_map.get(r.model_id or "", r.model_id or "unknown"),
            "provider": r.provider or "unknown",
            "input_tokens": int(r.input_tokens),
            "output_tokens": int(r.output_tokens),
            "calls": int(r.calls),
            "cost_cents": int(r.cost),
            "share": (r.cost / total) if total > 0 else 0,
        }
        for r in rows
    ]
    return {"window_days": days, "items": items, "total_cents": int(total)}


# ────────────── Expensive sessions ──────────────
async def expensive_sessions(
    db: AsyncSession,
    days: int = 30,
    limit: int = 20,
    min_cost_cents: int = 0,
) -> dict:
    cutoff = _utc_cutoff(days)
    cost_col = func.coalesce(func.sum(TokenUsage.cost_cents), 0).label("cost")
    rows = (
        await db.execute(
            select(
                GameSession.id,
                GameSession.user_id,
                GameSession.world_id,
                GameSession.rounds_played,
                GameSession.started_at,
                GameSession.last_played_at,
                GameSession.ended_at,
                User.nickname.label("nickname"),
                World.name.label("world_name"),
                cost_col,
            )
            .join(TokenUsage, TokenUsage.session_id == GameSession.id)
            .join(User, User.id == GameSession.user_id, isouter=True)
            .join(World, World.id == GameSession.world_id, isouter=True)
            .where(GameSession.started_at >= cutoff)
            .group_by(
                GameSession.id,
                GameSession.user_id,
                GameSession.world_id,
                GameSession.rounds_played,
                GameSession.started_at,
                GameSession.last_played_at,
                GameSession.ended_at,
                User.nickname,
                World.name,
            )
            .having(cost_col >= min_cost_cents)
            .order_by(desc("cost"))
            .limit(limit)
        )
    ).all()

    def _duration_minutes(started: datetime, ended: datetime | None, last_played: datetime) -> int:
        end = ended or last_played
        if not end or not started:
            return 0
        # 都按 naive UTC 处理（DB 列就是 timestamp without time zone）
        return int((end - started).total_seconds() / 60)

    items = [
        {
            "session_id": r.id,
            "user_id": r.user_id,
            "user_nickname": r.nickname,
            "world_id": r.world_id,
            "world_name": r.world_name,
            "rounds_played": int(r.rounds_played or 0),
            "started_at": serialize_utc_datetime(r.started_at),
            "last_played_at": serialize_utc_datetime(r.last_played_at),
            "ended_at": serialize_utc_datetime(r.ended_at),
            "duration_minutes": _duration_minutes(r.started_at, r.ended_at, r.last_played_at),
            "cost_cents": int(r.cost),
        }
        for r in rows
    ]
    return {"window_days": days, "items": items}


# ────────────── Cost KPIs ──────────────
async def cost_kpis(db: AsyncSession) -> dict:
    """Dashboard 用：今日 / 7 天 / 30 天总消耗 + 上一周期对比。

    日边界按北京时间计算，再转换成 naive UTC 与数据库列比较。
    """
    now = utcnow()
    today = beijing_day_start_utc(now)
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)
    two_weeks_ago = today - timedelta(days=14)
    month_ago = today - timedelta(days=30)
    two_months_ago = today - timedelta(days=60)

    async def _sum(start: datetime, end: datetime) -> int:
        return int(
            (
                await db.execute(
                    select(func.coalesce(func.sum(TokenUsage.cost_cents), 0)).where(
                        TokenUsage.created_at >= start, TokenUsage.created_at < end
                    )
                )
            ).scalar_one()
        )

    today_spend = await _sum(today, now)
    yesterday_spend = await _sum(yesterday, today)
    week_spend = await _sum(week_ago, now)
    prev_week_spend = await _sum(two_weeks_ago, week_ago)
    month_spend = await _sum(month_ago, now)
    prev_month_spend = await _sum(two_months_ago, month_ago)

    def _delta(curr: int, prev: int) -> float | None:
        if prev == 0:
            return None
        return round((curr - prev) / prev * 100, 1)

    return {
        "today_cents": today_spend,
        "today_delta_pct": _delta(today_spend, yesterday_spend),
        "week_cents": week_spend,
        "week_delta_pct": _delta(week_spend, prev_week_spend),
        "month_cents": month_spend,
        "month_delta_pct": _delta(month_spend, prev_month_spend),
    }


# ────────────── Cost by purpose ──────────────
async def cost_by_purpose(db: AsyncSession, days: int = 30) -> dict:
    """Spend grouped by the ``purpose`` label on each token_usage row.

    Buckets: game / moderation / reflection / compression / world_gen /
    script_gen / image_gen. For image_gen rows, ``image_count`` is the
    physical unit; for text rows it's tokens.
    """
    cutoff = _utc_cutoff(days)
    rows = (
        await db.execute(
            select(
                TokenUsage.purpose.label("purpose"),
                func.coalesce(func.sum(TokenUsage.cost_cents), 0).label("cost"),
                func.coalesce(func.sum(TokenUsage.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(TokenUsage.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(TokenUsage.image_count), 0).label("image_count"),
                func.count().label("calls"),
            )
            .where(TokenUsage.created_at >= cutoff)
            .group_by(TokenUsage.purpose)
            .order_by(desc("cost"))
        )
    ).all()
    total = sum(r.cost for r in rows)
    items = [
        {
            "purpose": r.purpose or "unknown",
            "cost_cents": int(r.cost),
            "input_tokens": int(r.input_tokens),
            "output_tokens": int(r.output_tokens),
            "image_count": int(r.image_count),
            "calls": int(r.calls),
            "share": (r.cost / total) if total > 0 else 0,
        }
        for r in rows
    ]
    return {"window_days": days, "items": items, "total_cents": int(total)}


# ────────────── Single generation task cost ──────────────
async def generation_task_cost(db: AsyncSession, task_id: str) -> dict:
    """Per-phase cost breakdown for one generation task.

    Returns a list of phase rows + a totals summary. ``phase`` may be
    null for rows that were not tagged with a sub-stage.
    """
    rows = (
        await db.execute(
            select(
                TokenUsage.phase.label("phase"),
                TokenUsage.purpose.label("purpose"),
                func.coalesce(func.sum(TokenUsage.cost_cents), 0).label("cost"),
                func.coalesce(func.sum(TokenUsage.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(TokenUsage.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(TokenUsage.image_count), 0).label("image_count"),
                func.count().label("calls"),
            )
            .where(TokenUsage.task_id == task_id)
            .group_by(TokenUsage.phase, TokenUsage.purpose)
            .order_by(desc("cost"))
        )
    ).all()
    items = [
        {
            "phase": r.phase,
            "purpose": r.purpose,
            "cost_cents": int(r.cost),
            "input_tokens": int(r.input_tokens),
            "output_tokens": int(r.output_tokens),
            "image_count": int(r.image_count),
            "calls": int(r.calls),
        }
        for r in rows
    ]
    return {
        "task_id": task_id,
        "items": items,
        "total_cost_cents": sum(item["cost_cents"] for item in items),
        "total_input_tokens": sum(item["input_tokens"] for item in items),
        "total_output_tokens": sum(item["output_tokens"] for item in items),
        "total_image_count": sum(item["image_count"] for item in items),
    }


# ────────────── Expensive generation tasks ──────────────
async def expensive_generation_tasks(
    db: AsyncSession,
    days: int = 30,
    limit: int = 20,
    min_cost_cents: int = 0,
) -> dict:
    """Top N most expensive generation tasks in the window."""
    cutoff = _utc_cutoff(days)
    cost_col = func.coalesce(func.sum(TokenUsage.cost_cents), 0).label("cost")
    rows = (
        await db.execute(
            select(
                GenerationTask.id,
                GenerationTask.kind,
                GenerationTask.status,
                GenerationTask.created_by_user_id,
                GenerationTask.created_at,
                GenerationTask.finished_at,
                User.nickname.label("nickname"),
                cost_col,
                func.count(TokenUsage.id).label("calls"),
            )
            .join(TokenUsage, TokenUsage.task_id == GenerationTask.id)
            .join(User, User.id == GenerationTask.created_by_user_id, isouter=True)
            .where(GenerationTask.created_at >= cutoff)
            .group_by(
                GenerationTask.id,
                GenerationTask.kind,
                GenerationTask.status,
                GenerationTask.created_by_user_id,
                GenerationTask.created_at,
                GenerationTask.finished_at,
                User.nickname,
            )
            .having(cost_col >= min_cost_cents)
            .order_by(desc("cost"))
            .limit(limit)
        )
    ).all()
    items = [
        {
            "task_id": r.id,
            "kind": r.kind,
            "status": r.status,
            "user_id": r.created_by_user_id,
            "user_nickname": r.nickname,
            "created_at": serialize_utc_datetime(r.created_at),
            "finished_at": serialize_utc_datetime(r.finished_at),
            "cost_cents": int(r.cost),
            "calls": int(r.calls),
        }
        for r in rows
    ]
    return {"window_days": days, "items": items}


__all__ = [
    "session_cost_summary",
    "generation_task_summary",
    "cost_trend_daily",
    "cost_by_provider",
    "cost_by_model",
    "expensive_sessions",
    "cost_kpis",
    "cost_by_purpose",
    "generation_task_cost",
    "expensive_generation_tasks",
]
