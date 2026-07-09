"""全站系统配置 service（单例行）。

目前承载「注册放量」：批次模式下统计 ``signup_batch_start`` 之后新建的账号数，
满额即拒。计数直接打在 ``users`` 表上——邮箱注册和 OAuth 首登都会建 User 行，
所以一处计数自然覆盖两个注册入口。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from middleware.error_handler import AppError
from models.system_config import SYSTEM_CONFIG_ID, SystemConfig
from models.user import User
from utils import utcnow

SIGNUP_MODES = {"open", "capped", "closed"}
IMAGE_QUALITIES = {"low", "medium", "high", "auto"}

RUNTIME_CONFIG_FIELDS = (
    "llm_global_concurrency",
    "llm_call_timeout_seconds",
    "llm_call_max_retries",
    "llm_call_retry_backoff_seconds",
    "generation_task_active_limit_per_user",
    "image_generation_concurrency",
    "image_generation_global_concurrency",
    "image_generation_timeout_seconds",
    "image_generation_quality",
    "lore_pack_concurrency",
    "character_batch_concurrency",
    "events_data_concurrency",
)


async def get_config(db: AsyncSession) -> SystemConfig:
    """读取单例配置，缺失时建默认行（get-or-create）。"""
    cfg = await db.get(SystemConfig, SYSTEM_CONFIG_ID)
    if cfg is None:
        cfg = SystemConfig(
            id=SYSTEM_CONFIG_ID,
            signup_mode="open",
            signup_cap=0,
            llm_global_concurrency=settings.llm_global_concurrency,
            llm_call_timeout_seconds=settings.llm_call_timeout_seconds,
            llm_call_max_retries=settings.llm_call_max_retries,
            llm_call_retry_backoff_seconds=settings.llm_call_retry_backoff_seconds,
            generation_task_active_limit_per_user=settings.generation_task_active_limit_per_user,
            image_generation_concurrency=settings.image_generation_concurrency,
            image_generation_global_concurrency=settings.image_generation_global_concurrency,
            image_generation_timeout_seconds=settings.image_generation_timeout_seconds,
            image_generation_quality=settings.image_generation_quality,
            lore_pack_concurrency=settings.lore_pack_concurrency,
            character_batch_concurrency=settings.character_batch_concurrency,
            events_data_concurrency=settings.events_data_concurrency,
        )
        db.add(cfg)
        await db.flush()
    return cfg


def _runtime_config_payload(cfg: SystemConfig) -> dict:
    return {
        **{field: getattr(cfg, field) for field in RUNTIME_CONFIG_FIELDS},
        "updated_at": cfg.updated_at,
    }


def apply_runtime_config(cfg: SystemConfig) -> None:
    """Apply DB-backed runtime knobs to the process-level settings object.

    Most runtime call sites already read ``config.settings`` lazily. Updating it
    here keeps env as a bootstrap default while making admin changes live for
    new LLM/image calls in this process.
    """
    for field in RUNTIME_CONFIG_FIELDS:
        setattr(settings, field, getattr(cfg, field))


async def load_runtime_config(db: AsyncSession) -> dict:
    cfg = await get_config(db)
    apply_runtime_config(cfg)
    return _runtime_config_payload(cfg)


async def runtime_config_status(db: AsyncSession) -> dict:
    cfg = await get_config(db)
    return _runtime_config_payload(cfg)


async def update_runtime_config(
    db: AsyncSession,
    *,
    admin_id: str,
    values: dict,
) -> SystemConfig:
    cfg = await get_config(db)
    for field in RUNTIME_CONFIG_FIELDS:
        if field not in values:
            continue
        value = values[field]
        if field == "image_generation_quality":
            value = str(value).strip().lower()
            if value not in IMAGE_QUALITIES:
                raise AppError(42232, "未知的图片质量", status_code=422)
        setattr(cfg, field, value)
    cfg.updated_by = admin_id
    await db.flush()
    return cfg


async def _signups_in_batch(db: AsyncSession, since: datetime) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(User).where(User.created_at >= since)
        )
    ).scalar_one()


async def signup_status(db: AsyncSession) -> dict:
    """admin 视角：当前放量配置 + 本批已注册 / 剩余名额。"""
    cfg = await get_config(db)
    used = 0
    remaining: int | None = None
    if cfg.signup_mode == "capped" and cfg.signup_batch_start is not None:
        used = await _signups_in_batch(db, cfg.signup_batch_start)
        remaining = max(cfg.signup_cap - used, 0)
    return {
        "signup_mode": cfg.signup_mode,
        "signup_cap": cfg.signup_cap,
        "signup_batch_start": cfg.signup_batch_start,
        "batch_used": used,
        "batch_remaining": remaining,
        "updated_at": cfg.updated_at,
    }


async def ensure_signup_allowed(db: AsyncSession) -> None:
    """注册闸门：在「即将新建账号」前调用。被拦则抛 AppError。

    幂等再注册（已存在未验证身份）不应调用本函数——那不产生新账号。
    """
    cfg = await get_config(db)
    if cfg.signup_mode == "open":
        return
    if cfg.signup_mode == "closed":
        raise AppError(40310, "注册暂未开放，敬请期待", status_code=403)
    # capped
    if cfg.signup_batch_start is None:
        # 配成 capped 却没开批次 = 视为未开放，避免误放
        raise AppError(40310, "注册暂未开放，敬请期待", status_code=403)
    used = await _signups_in_batch(db, cfg.signup_batch_start)
    if used >= cfg.signup_cap:
        raise AppError(40311, "本批注册名额已满，请关注后续开放", status_code=403)


async def update_signup_config(
    db: AsyncSession,
    *,
    admin_id: str,
    signup_mode: str | None = None,
    signup_cap: int | None = None,
    start_new_batch: bool = False,
) -> SystemConfig:
    """更新注册放量配置。

    ``start_new_batch=True`` 把计数起点重置为 now（= 「从现在起再放 N 人」/「开新一批」）。
    切到 capped 且从未设过批次起点时，自动以 now 起算。
    """
    cfg = await get_config(db)
    if signup_mode is not None:
        if signup_mode not in SIGNUP_MODES:
            raise AppError(42230, "未知的注册模式", status_code=422)
        cfg.signup_mode = signup_mode
    if signup_cap is not None:
        if signup_cap < 0:
            raise AppError(42231, "名额不能为负", status_code=422)
        cfg.signup_cap = signup_cap
    if start_new_batch or (cfg.signup_mode == "capped" and cfg.signup_batch_start is None):
        cfg.signup_batch_start = utcnow()
    cfg.updated_by = admin_id
    await db.flush()
    return cfg
