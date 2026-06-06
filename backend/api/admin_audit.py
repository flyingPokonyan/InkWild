from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_admin_user
from models.audit_log import AdminAuditLog
from models.user import User

router = APIRouter(
    prefix="/api/admin/audit-logs",
    tags=["admin-audit"],
    dependencies=[Depends(get_current_admin_user)],
)


def _serialize(log: AdminAuditLog, admin: User | None) -> dict:
    return {
        "id": log.id,
        "admin_user_id": log.admin_user_id,
        "admin": (
            {
                "id": admin.id,
                "nickname": admin.nickname,
            }
            if admin is not None
            else None
        ),
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "payload": log.payload,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "created_at": log.created_at.isoformat(),
    }


@router.get("")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    action_prefix: str | None = Query(
        None,
        description="按 action 命名空间筛选，例如 'model_provider' 匹配所有 model_provider.* 记录",
    ),
    admin_user_id: str | None = Query(None),
    resource_type: str | None = Query(None),
    resource_id: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    filters = []
    if action_prefix:
        filters.append(AdminAuditLog.action.like(f"{action_prefix}.%"))
    if admin_user_id:
        filters.append(AdminAuditLog.admin_user_id == admin_user_id)
    if resource_type:
        filters.append(AdminAuditLog.resource_type == resource_type)
    if resource_id:
        filters.append(AdminAuditLog.resource_id == resource_id)
    # DB 列是 timestamp without time zone，前端会传 ISO Z 后缀（tz-aware），剥掉。
    if since:
        filters.append(
            AdminAuditLog.created_at >= since.replace(tzinfo=None)
        )
    if until:
        filters.append(
            AdminAuditLog.created_at < until.replace(tzinfo=None)
        )

    count_stmt = select(func.count()).select_from(AdminAuditLog)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    rows_stmt = select(AdminAuditLog, User).outerjoin(
        User, AdminAuditLog.admin_user_id == User.id
    )
    if filters:
        rows_stmt = rows_stmt.where(*filters)
    rows_stmt = (
        rows_stmt.order_by(AdminAuditLog.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await db.execute(rows_stmt)).all()
    items = [_serialize(log, admin) for log, admin in rows]

    return {
        "code": 0,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        },
        "message": "ok",
    }


@router.get("/namespaces")
async def list_action_namespaces(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """所有 action 命名空间（action 中第一个 '.' 之前的部分），用于前端筛选下拉。"""
    stmt = select(
        distinct(func.split_part(AdminAuditLog.action, ".", 1)).label("ns")
    ).order_by("ns")
    namespaces = [ns for (ns,) in (await db.execute(stmt)).all() if ns]
    return {"code": 0, "data": namespaces, "message": "ok"}
