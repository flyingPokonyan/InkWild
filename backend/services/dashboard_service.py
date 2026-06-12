from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.draft import ScriptDraft, WorldDraft
from models.game import GameSession
from models.generation_task import GenerationTask
from models.model_management import ProviderModel
from models.script import Script
from models.user import AuthIdentity, User
from models.world import World

from services.analytics_service import cost_kpis
from utils import utcnow


async def _scalar(db: AsyncSession, stmt) -> int:
    return int((await db.execute(stmt)).scalar_one())


async def dashboard_kpis(db: AsyncSession) -> dict:
    """所有 Dashboard 卡片需要的指标，一次查询返回。"""
    now = utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    cost = await cost_kpis(db)

    active_sessions = await _scalar(
        db,
        select(func.count()).select_from(GameSession).where(
            GameSession.last_played_at >= day_ago,
            GameSession.status == "playing",
        ),
    )

    failed_gens_24h = await _scalar(
        db,
        select(func.count()).select_from(GenerationTask).where(
            GenerationTask.created_at >= day_ago,
            GenerationTask.status == "failed",
        ),
    )

    new_users_7d = await _scalar(
        db,
        select(func.count(func.distinct(AuthIdentity.user_id))).where(
            AuthIdentity.verified_at >= week_ago
        ),
    )

    new_worlds_7d = await _scalar(
        db,
        select(func.count()).select_from(World).where(
            World.created_at >= week_ago,
            World.status == "published",
        ),
    )

    new_scripts_7d = await _scalar(
        db,
        select(func.count()).select_from(Script).where(
            Script.created_at >= week_ago,
            Script.is_published.is_(True),
        ),
    )

    # Enabled models 缺单价：text 缺 input/output、image 缺 image 单价
    missing_pricing = await _scalar(
        db,
        select(func.count())
        .select_from(ProviderModel)
        .where(
            ProviderModel.is_enabled.is_(True),
            or_(
                and_(
                    ProviderModel.model_kind == "text",
                    or_(
                        ProviderModel.input_price_cents_per_million_tokens.is_(None),
                        ProviderModel.output_price_cents_per_million_tokens.is_(None),
                    ),
                ),
                and_(
                    ProviderModel.model_kind == "image",
                    ProviderModel.image_price_cents_per_image.is_(None),
                ),
            ),
        ),
    )

    pending_reviews = await _scalar(
        db,
        select(func.count())
        .select_from(WorldDraft)
        .where(WorldDraft.review_status == "submitted"),
    ) + await _scalar(
        db,
        select(func.count())
        .select_from(ScriptDraft)
        .where(ScriptDraft.review_status == "submitted"),
    )

    return {
        "spend": cost,
        "active_sessions_24h": active_sessions,
        "failed_generations_24h": failed_gens_24h,
        "new_users_7d": new_users_7d,
        "new_worlds_7d": new_worlds_7d,
        "new_scripts_7d": new_scripts_7d,
        "models_missing_pricing": missing_pricing,
        "pending_reviews": pending_reviews,
    }


__all__ = ["dashboard_kpis"]
