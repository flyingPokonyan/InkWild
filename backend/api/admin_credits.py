"""Admin credit management: per-user view + manual adjust (escape valve) and
live-editable economy config (multiplier / grant / estimates).

All writes are audited via ``record_admin_action``. Config is read fresh by
``credit_service.get_config`` on every gate/settle, so edits take effect live.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_admin_user, get_db
from models.credit import CreditConfig, CreditLedger
from models.user import User
from services import credit_service
from services.audit_service import record_admin_action
from services.credit_pricing import credits_to_units, units_to_credits
from utils import serialize_utc_datetime

router = APIRouter(prefix="/api/admin", tags=["admin-credits"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _ledger_item(r: CreditLedger) -> dict:
    return {
        "id": r.id,
        "ts": serialize_utc_datetime(r.created_at),
        "kind": r.kind,
        "category": r.category,
        "delta": units_to_credits(r.delta_units),
        "balance_after": units_to_credits(r.balance_after_units),
        "cost_cents": r.cost_cents,
        "note": r.note,
        "ref_type": r.ref_type,
        "ref_id": r.ref_id,
    }


class AdjustRequest(BaseModel):
    delta_credits: float
    note: str | None = None


@router.get("/users/{user_id}/credits")
async def get_user_credits(
    user_id: str,
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    wallet = await credit_service.get_or_create_wallet(db, user_id)
    rows = (
        await db.execute(
            select(CreditLedger)
            .where(CreditLedger.user_id == user_id)
            .order_by(CreditLedger.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    return {
        "code": 0,
        "data": {
            "balance": units_to_credits(wallet.balance_units),
            "lifetime_granted": units_to_credits(wallet.lifetime_granted_units),
            "lifetime_spent": units_to_credits(wallet.lifetime_spent_units),
            "ledger": [_ledger_item(r) for r in rows],
        },
        "message": "ok",
    }


@router.post("/users/{user_id}/credits/adjust")
async def adjust_user_credits(
    user_id: str,
    payload: AdjustRequest,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not payload.delta_credits:
        raise HTTPException(status_code=400, detail="delta_credits 不能为 0")

    delta_units = credits_to_units(payload.delta_credits)
    new_balance = await credit_service.grant(
        db,
        user_id,
        delta_units,
        kind="admin_adjust",
        category="adjust",
        note=payload.note,
        actor_user_id=admin.id,
    )
    await record_admin_action(
        db,
        admin_user=admin,
        action="credit.adjust",
        resource_type="user",
        resource_id=user_id,
        payload={"delta_credits": payload.delta_credits, "note": payload.note},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    return {"code": 0, "data": {"balance": units_to_credits(new_balance)}, "message": "ok"}


class ConfigUpdate(BaseModel):
    billing_multiplier: float | None = None  # 1.0 == break-even
    signup_grant: float | None = None  # credits
    estimate_game: float | None = None  # credits
    estimate_world: float | None = None  # credits
    estimate_script: float | None = None  # credits
    gate_fail_mode: str | None = None  # 'open' | 'safe'


def _config_data(row: CreditConfig | None) -> dict:
    cfg = credit_service._DEFAULT_CONFIG
    multiplier_milli = row.billing_multiplier_milli if row else cfg.billing_multiplier_milli
    return {
        "billing_multiplier": round(multiplier_milli / 1000, 3),
        "signup_grant": units_to_credits(row.signup_grant_units if row else cfg.signup_grant_units),
        "estimate_game": units_to_credits(row.estimate_game_units if row else cfg.estimate_game_units),
        "estimate_world": units_to_credits(row.estimate_world_units if row else cfg.estimate_world_units),
        "estimate_script": units_to_credits(row.estimate_script_units if row else cfg.estimate_script_units),
        "gate_fail_mode": (row.gate_fail_mode if row else cfg.gate_fail_mode) or "open",
    }


@router.get("/credits/config")
async def get_credit_config(
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(CreditConfig, 1)
    return {"code": 0, "data": _config_data(row), "message": "ok"}


@router.put("/credits/config")
async def update_credit_config(
    payload: ConfigUpdate,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(CreditConfig, 1)
    if row is None:
        row = CreditConfig(id=1)
        db.add(row)

    changes: dict = {}
    if payload.billing_multiplier is not None:
        if payload.billing_multiplier <= 0:
            raise HTTPException(status_code=400, detail="billing_multiplier 必须 > 0")
        row.billing_multiplier_milli = round(payload.billing_multiplier * 1000)
        changes["billing_multiplier"] = payload.billing_multiplier
    if payload.signup_grant is not None:
        row.signup_grant_units = credits_to_units(payload.signup_grant)
        changes["signup_grant"] = payload.signup_grant
    if payload.estimate_game is not None:
        row.estimate_game_units = credits_to_units(payload.estimate_game)
        changes["estimate_game"] = payload.estimate_game
    if payload.estimate_world is not None:
        row.estimate_world_units = credits_to_units(payload.estimate_world)
        changes["estimate_world"] = payload.estimate_world
    if payload.estimate_script is not None:
        row.estimate_script_units = credits_to_units(payload.estimate_script)
        changes["estimate_script"] = payload.estimate_script
    if payload.gate_fail_mode is not None:
        if payload.gate_fail_mode not in ("open", "safe"):
            raise HTTPException(status_code=400, detail="gate_fail_mode 必须是 open 或 safe")
        row.gate_fail_mode = payload.gate_fail_mode
        changes["gate_fail_mode"] = payload.gate_fail_mode

    await record_admin_action(
        db,
        admin_user=admin,
        action="credit.config_update",
        resource_type="credit_config",
        resource_id="1",
        payload={"changes": changes},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    return {"code": 0, "data": _config_data(row), "message": "ok"}


def _drift_count(report) -> int:
    rows = report if isinstance(report, list) else [report]
    return sum(1 for r in rows if r.get("balance_drift") or r.get("held_drift"))


@router.get("/credits/reconcile")
async def reconcile_credits(
    user_id: str | None = None,
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dry-run: verify wallet invariants (balance==Σledger, held==Σ active holds)."""
    report = await credit_service.reconcile(db, user_id=user_id, repair=False)
    return {
        "code": 0,
        "data": {"report": report, "drift_count": _drift_count(report)},
        "message": "ok",
    }


@router.post("/credits/reconcile")
async def repair_credits(
    request: Request,
    user_id: str | None = None,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Repair: re-derive wallet balance/held from the authoritative sources."""
    report = await credit_service.reconcile(db, user_id=user_id, repair=True)
    drift_count = _drift_count(report)
    await record_admin_action(
        db,
        admin_user=admin,
        action="credit.reconcile",
        resource_type="credit_wallet",
        resource_id=user_id or "all",
        payload={"user_id": user_id, "drift_count": drift_count},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    return {
        "code": 0,
        "data": {"report": report, "drift_count": drift_count},
        "message": "ok",
    }
