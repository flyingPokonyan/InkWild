from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_admin_user, get_db
from models.user import User
from services import analytics_service

router = APIRouter(prefix="/api/admin/analytics", tags=["admin-analytics"])


@router.get("/sessions")
async def get_session_summary(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    return {
        "code": 0,
        "data": await analytics_service.session_cost_summary(db, days=days),
        "message": "ok",
    }


@router.get("/generations")
async def get_generation_summary(
    days: int = Query(7, ge=1, le=90),
    kind: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    return {
        "code": 0,
        "data": await analytics_service.generation_task_summary(db, days=days, kind=kind),
        "message": "ok",
    }


@router.get("/cost-trend")
async def get_cost_trend(
    days: int = Query(30, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    return {
        "code": 0,
        "data": await analytics_service.cost_trend_daily(db, days=days),
        "message": "ok",
    }


@router.get("/cost-by-provider")
async def get_cost_by_provider(
    days: int = Query(30, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    return {
        "code": 0,
        "data": await analytics_service.cost_by_provider(db, days=days),
        "message": "ok",
    }


@router.get("/cost-by-model")
async def get_cost_by_model(
    days: int = Query(30, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    return {
        "code": 0,
        "data": await analytics_service.cost_by_model(db, days=days),
        "message": "ok",
    }


@router.get("/expensive-sessions")
async def get_expensive_sessions(
    days: int = Query(30, ge=1, le=180),
    limit: int = Query(20, ge=1, le=100),
    min_cost_cents: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    return {
        "code": 0,
        "data": await analytics_service.expensive_sessions(
            db, days=days, limit=limit, min_cost_cents=min_cost_cents
        ),
        "message": "ok",
    }


@router.get("/cost-kpis")
async def get_cost_kpis(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    return {
        "code": 0,
        "data": await analytics_service.cost_kpis(db),
        "message": "ok",
    }


@router.get("/cost-by-purpose")
async def get_cost_by_purpose(
    days: int = Query(30, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    return {
        "code": 0,
        "data": await analytics_service.cost_by_purpose(db, days=days),
        "message": "ok",
    }


@router.get("/generation-tasks/{task_id}/cost")
async def get_generation_task_cost(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    return {
        "code": 0,
        "data": await analytics_service.generation_task_cost(db, task_id),
        "message": "ok",
    }


@router.get("/expensive-generation-tasks")
async def get_expensive_generation_tasks(
    days: int = Query(30, ge=1, le=180),
    limit: int = Query(20, ge=1, le=100),
    min_cost_cents: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    return {
        "code": 0,
        "data": await analytics_service.expensive_generation_tasks(
            db, days=days, limit=limit, min_cost_cents=min_cost_cents
        ),
        "message": "ok",
    }
