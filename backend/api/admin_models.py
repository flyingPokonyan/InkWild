from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_admin_user, get_db
from models.model_management import ProviderModel
from models.user import User
from services.audit_service import record_admin_action
from services.model_management import (
    ModelManagementError,
    bind_model_slot,
    create_model_provider,
    create_provider_model,
    delete_model_provider,
    delete_provider_model,
    get_model_dashboard,
    healthcheck_model_provider,
    list_model_providers,
    list_model_slots,
    list_provider_models,
    probe_model_capabilities,
    update_model_provider,
    update_provider_model,
)
from utils import utcnow

router = APIRouter(prefix="/api/admin", tags=["admin-models"], dependencies=[Depends(get_current_admin_user)])


class CreateModelProviderRequest(BaseModel):
    name: str
    provider_type: str
    base_url: str | None = None
    api_key_env_name: str | None = None
    # None=不变（编辑时）；[]=清空；[...]=整组替换。原始 key，响应永不回显。
    api_keys: list[str] | None = None
    extra_config: dict = Field(default_factory=dict)


class UpdateModelProviderRequest(CreateModelProviderRequest):
    status: str = "active"


class CreateProviderModelRequest(BaseModel):
    provider_id: str
    model_id: str
    display_name: str
    model_kind: str
    is_enabled: bool = True
    notes: str | None = None
    input_price_cents_per_million_tokens: int | None = None
    output_price_cents_per_million_tokens: int | None = None
    image_price_cents_per_image: int | None = None


class UpdateProviderModelRequest(BaseModel):
    display_name: str
    model_kind: str
    is_enabled: bool = True
    notes: str | None = None
    input_price_cents_per_million_tokens: int | None = None
    output_price_cents_per_million_tokens: int | None = None
    image_price_cents_per_image: int | None = None


class ProbeProviderModelRequest(BaseModel):
    capabilities: list[str]


class BindModelSlotRequest(BaseModel):
    model_id: str | None = None


def _apply_pricing_fields(model: ProviderModel, payload) -> None:
    changed = False
    for fname in ("input_price_cents_per_million_tokens", "output_price_cents_per_million_tokens", "image_price_cents_per_image"):
        new_val = getattr(payload, fname, None)
        if new_val != getattr(model, fname):
            setattr(model, fname, new_val)
            changed = True
    if changed:
        model.price_updated_at = utcnow()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, ModelManagementError):
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    if isinstance(exc, IntegrityError):
        raise HTTPException(status_code=400, detail="记录冲突，请检查名称或模型是否重复") from exc
    raise exc


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.get("/model-dashboard")
async def get_model_dashboard_route(db: AsyncSession = Depends(get_db)):
    return {"code": 0, "data": await get_model_dashboard(db)}


@router.get("/model-providers")
async def get_model_providers(db: AsyncSession = Depends(get_db)):
    return {"code": 0, "data": await list_model_providers(db)}


@router.post("/model-providers")
async def post_model_provider(
    req: CreateModelProviderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    try:
        provider = await create_model_provider(
            db,
            name=req.name,
            provider_type=req.provider_type,
            base_url=req.base_url,
            api_key_env_name=req.api_key_env_name,
            api_keys=req.api_keys,
            extra_config=req.extra_config,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http_error(exc)
    await record_admin_action(
        db,
        admin_user=admin_user,
        action="model_provider.create",
        resource_type="model_provider",
        resource_id=provider.get("id"),
        payload={"name": req.name, "provider_type": req.provider_type},
        ip_address=_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    await db.commit()
    return {"code": 0, "data": {"provider": provider}}


@router.put("/model-providers/{provider_id}")
async def put_model_provider(
    provider_id: str,
    req: UpdateModelProviderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    try:
        provider = await update_model_provider(
            db,
            provider_id,
            name=req.name,
            provider_type=req.provider_type,
            base_url=req.base_url,
            api_key_env_name=req.api_key_env_name,
            api_keys=req.api_keys,
            extra_config=req.extra_config,
            status=req.status,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http_error(exc)
    await record_admin_action(
        db,
        admin_user=admin_user,
        action="model_provider.update",
        resource_type="model_provider",
        resource_id=provider_id,
        payload={"name": req.name, "provider_type": req.provider_type, "status": req.status},
        ip_address=_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    await db.commit()
    return {"code": 0, "data": {"provider": provider}}


@router.delete("/model-providers/{provider_id}")
async def remove_model_provider(
    provider_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    try:
        result = await delete_model_provider(db, provider_id)
    except Exception as exc:  # noqa: BLE001
        _raise_http_error(exc)
    await record_admin_action(
        db,
        admin_user=admin_user,
        action="model_provider.delete",
        resource_type="model_provider",
        resource_id=provider_id,
        payload=result,
        ip_address=_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    await db.commit()
    return {"code": 0, "data": result, "message": "ok"}


@router.post("/model-providers/{provider_id}/healthcheck")
async def post_model_provider_healthcheck(
    provider_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    try:
        result = await healthcheck_model_provider(db, provider_id)
    except Exception as exc:  # noqa: BLE001
        _raise_http_error(exc)
    await record_admin_action(
        db,
        admin_user=admin_user,
        action="model_provider.healthcheck",
        resource_type="model_provider",
        resource_id=provider_id,
        payload={"ok": result.get("ok"), "error": result.get("error")},
        ip_address=_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    await db.commit()
    return {"code": 0, "data": result}


@router.get("/provider-models")
async def get_provider_models(provider_id: str | None = None, db: AsyncSession = Depends(get_db)):
    return {"code": 0, "data": await list_provider_models(db, provider_id=provider_id)}


@router.post("/provider-models")
async def post_provider_model(
    req: CreateProviderModelRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    # Compute price_updated_at before the service call so we don't need ORM access after.
    _price_ts = utcnow() if any(
        getattr(req, f) is not None
        for f in ("input_price_cents_per_million_tokens", "output_price_cents_per_million_tokens", "image_price_cents_per_image")
    ) else None
    try:
        model = await create_provider_model(
            db,
            provider_id=req.provider_id,
            model_id=req.model_id,
            display_name=req.display_name,
            model_kind=req.model_kind,
            is_enabled=req.is_enabled,
            notes=req.notes,
            input_price_cents_per_million_tokens=req.input_price_cents_per_million_tokens,
            output_price_cents_per_million_tokens=req.output_price_cents_per_million_tokens,
            image_price_cents_per_image=req.image_price_cents_per_image,
            price_updated_at=_price_ts,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http_error(exc)
    await record_admin_action(
        db,
        admin_user=admin_user,
        action="provider_model.create",
        resource_type="provider_model",
        resource_id=model.get("id"),
        payload={"provider_id": req.provider_id, "model_id": req.model_id, "model_kind": req.model_kind},
        ip_address=_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    await db.commit()
    return {"code": 0, "data": {"model": model}}


@router.put("/provider-models/{model_id}")
async def put_provider_model(
    model_id: str,
    req: UpdateProviderModelRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    # Detect pricing change against the current DB state to decide whether to bump price_updated_at.
    # 在 rollback 之前先抠出 admin_user.id —— rollback 会 expire 当前 session 所有对象，
    # 后续 record_admin_action 再 touch admin_user.id 会触发 lazy load 报 greenlet 错。
    _admin_user_id = admin_user.id
    _existing = await db.get(ProviderModel, model_id)
    _price_ts = None
    if _existing is not None:
        _apply_pricing_fields(_existing, req)
        _price_ts = _existing.price_updated_at
        # Expire the cached state so the service re-fetches cleanly.
        await db.rollback()
        # rollback 后重新载入 admin_user，避免后续访问其属性出错。
        admin_user = await db.get(User, _admin_user_id)
    try:
        model = await update_provider_model(
            db,
            model_id,
            display_name=req.display_name,
            model_kind=req.model_kind,
            is_enabled=req.is_enabled,
            notes=req.notes,
            input_price_cents_per_million_tokens=req.input_price_cents_per_million_tokens,
            output_price_cents_per_million_tokens=req.output_price_cents_per_million_tokens,
            image_price_cents_per_image=req.image_price_cents_per_image,
            price_updated_at=_price_ts,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_http_error(exc)
    await record_admin_action(
        db,
        admin_user=admin_user,
        action="provider_model.update",
        resource_type="provider_model",
        resource_id=model_id,
        payload={"display_name": req.display_name, "model_kind": req.model_kind, "is_enabled": req.is_enabled},
        ip_address=_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    await db.commit()
    return {"code": 0, "data": {"model": model}}


@router.delete("/provider-models/{model_id}")
async def remove_provider_model(
    model_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    try:
        await delete_provider_model(db, model_id)
    except Exception as exc:  # noqa: BLE001
        _raise_http_error(exc)
    await record_admin_action(
        db,
        admin_user=admin_user,
        action="provider_model.delete",
        resource_type="provider_model",
        resource_id=model_id,
        ip_address=_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    await db.commit()
    return {"code": 0, "message": "ok"}


@router.post("/provider-models/{model_id}/probe")
async def post_provider_model_probe(
    model_id: str,
    req: ProbeProviderModelRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    try:
        result = await probe_model_capabilities(db, model_id=model_id, capabilities=req.capabilities)
    except Exception as exc:  # noqa: BLE001
        _raise_http_error(exc)
    await record_admin_action(
        db,
        admin_user=admin_user,
        action="provider_model.probe",
        resource_type="provider_model",
        resource_id=model_id,
        payload={"capabilities": req.capabilities},
        ip_address=_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    await db.commit()
    return {"code": 0, "data": result}


@router.get("/model-slots")
async def get_model_slots(db: AsyncSession = Depends(get_db)):
    return {"code": 0, "data": await list_model_slots(db)}


@router.put("/model-slots/{slot_name}")
async def put_model_slot(
    slot_name: str,
    req: BindModelSlotRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    try:
        slot = await bind_model_slot(db, slot_name=slot_name, model_id=req.model_id)
    except Exception as exc:  # noqa: BLE001
        _raise_http_error(exc)
    await record_admin_action(
        db,
        admin_user=admin_user,
        action="model_slot.bind",
        resource_type="model_slot",
        resource_id=slot_name,
        payload={"model_id": req.model_id},
        ip_address=_client_ip(request),
        user_agent=_request_user_agent(request),
    )
    await db.commit()
    return {"code": 0, "data": {"slot": slot}}
