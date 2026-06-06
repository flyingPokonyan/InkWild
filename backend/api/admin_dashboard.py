from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_admin_user
from services import dashboard_service

router = APIRouter(
    prefix="/api/admin/dashboard",
    tags=["admin-dashboard"],
    dependencies=[Depends(get_current_admin_user)],
)


@router.get("/kpis")
async def get_kpis(db: AsyncSession = Depends(get_db)) -> dict:
    return {
        "code": 0,
        "data": await dashboard_service.dashboard_kpis(db),
        "message": "ok",
    }
