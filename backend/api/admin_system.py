"""Admin 系统配置：注册放量控制。

写操作经 ``record_admin_action`` 审计。GET 返回当前放量配置 + 本批已用 / 剩余名额。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_admin_user, get_db
from models.user import User
from schemas.system_config import (
    RuntimeConfigOut,
    RuntimeConfigUpdateIn,
    SignupConfigUpdateIn,
    SignupStatusOut,
)
from services import system_config_service as svc
from services.audit_service import record_admin_action

router = APIRouter(prefix="/api/admin", tags=["admin-system"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _ok(data) -> dict:
    return {"code": 0, "data": data, "message": "ok"}


@router.get("/system/signup")
async def get_signup_config(
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    status = await svc.signup_status(db)
    return _ok(SignupStatusOut.model_validate(status).model_dump(mode="json"))


@router.put("/system/signup")
async def update_signup_config(
    payload: SignupConfigUpdateIn,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await svc.update_signup_config(
        db,
        admin_id=admin.id,
        signup_mode=payload.signup_mode,
        signup_cap=payload.signup_cap,
        start_new_batch=payload.start_new_batch,
    )
    await record_admin_action(
        db,
        admin_user=admin,
        action="system.signup.update",
        resource_type="system_config",
        resource_id="signup",
        payload=payload.model_dump(exclude_none=True, mode="json"),
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    status = await svc.signup_status(db)
    return _ok(SignupStatusOut.model_validate(status).model_dump(mode="json"))


@router.get("/system/runtime")
async def get_runtime_config(
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    status = await svc.runtime_config_status(db)
    return _ok(RuntimeConfigOut.model_validate(status).model_dump(mode="json"))


@router.put("/system/runtime")
async def update_runtime_config(
    payload: RuntimeConfigUpdateIn,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    values = payload.model_dump(exclude_none=True)
    cfg = await svc.update_runtime_config(
        db,
        admin_id=admin.id,
        values=values,
    )
    await record_admin_action(
        db,
        admin_user=admin,
        action="system.runtime.update",
        resource_type="system_config",
        resource_id="runtime",
        payload=values,
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    svc.apply_runtime_config(cfg)
    status = await svc.runtime_config_status(db)
    return _ok(RuntimeConfigOut.model_validate(status).model_dump(mode="json"))
