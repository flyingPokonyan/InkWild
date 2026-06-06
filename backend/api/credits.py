"""User-facing credits API: balance + transaction history.

Debit rows are written at action granularity (one per game turn / generation),
so the ledger is already a clean per-action statement — no grouping needed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user, get_db
from models.credit import CreditLedger
from models.draft import ScriptDraft, WorldDraft
from models.game import GameSession
from models.generation_task import GenerationTask
from models.script import Script
from models.user import User
from models.world import World
from services import credit_service
from services.credit_pricing import units_to_credits

router = APIRouter(prefix="/api/credits", tags=["credits"])

_LEDGER_CATEGORIES = {"play", "creation", "image", "grant", "adjust"}


def _parse_category_filter(category: str | None) -> list[str] | None:
    if not category or not category.strip():
        return None
    requested = [part.strip() for part in category.split(",") if part.strip()]
    return [part for part in requested if part in _LEDGER_CATEGORIES]


async def _enrich_refs(db: AsyncSession, user_id: str, items: list[dict]) -> None:
    """Attach human-readable context to each ledger row, in place.

    Read-only, batched (no N+1). Resolves a debit's ``ref`` to the entity it was
    for — world/script name for play, generated work name for creation — plus a
    per-run turn ordinal — so the ledger reads as a real statement instead of a
    wall of identical "游玩消耗 −25" rows. Rows whose ref is missing/deleted keep
    their null fields and fall back to the bare kind label on the client.
    """
    session_ids = {it["ref_id"] for it in items if it["ref_type"] == "session" and it["ref_id"]}
    task_ids = {it["ref_id"] for it in items if it["ref_type"] == "task" and it["ref_id"]}

    sess_map: dict[str, tuple[str, str | None, str | None]] = {}
    turn_map: dict[str, int] = {}
    if session_ids:
        rows = (
            await db.execute(
                select(GameSession.id, GameSession.mode, World.name, Script.name)
                .select_from(GameSession)
                .outerjoin(World, World.id == GameSession.world_id)
                .outerjoin(Script, Script.id == GameSession.script_id)
                .where(GameSession.id.in_(session_ids))
            )
        ).all()
        sess_map = {sid: (mode, world_name, script_name) for sid, mode, world_name, script_name in rows}
        # 回合序号：该局所有游玩流水按时间编号（含失败未扣费的尝试）→ 老记录也能显示。
        ranked = (
            select(
                CreditLedger.id.label("id"),
                func.row_number()
                .over(partition_by=CreditLedger.ref_id, order_by=CreditLedger.created_at)
                .label("turn"),
            )
            .where(
                CreditLedger.user_id == user_id,
                CreditLedger.ref_type == "session",
                CreditLedger.ref_id.in_(session_ids),
                CreditLedger.category == "play",
            )
            .subquery()
        )
        page_ids = [it["id"] for it in items if it["ref_type"] == "session"]
        if page_ids:
            turn_rows = (
                await db.execute(select(ranked.c.id, ranked.c.turn).where(ranked.c.id.in_(page_ids)))
            ).all()
            turn_map = {rid: int(turn) for rid, turn in turn_rows}

    task_name: dict[str, str] = {}
    if task_ids:
        task_rows = (
            await db.execute(
                select(GenerationTask.id, GenerationTask.draft_type, GenerationTask.draft_id).where(
                    GenerationTask.id.in_(task_ids)
                )
            )
        ).all()
        world_draft_ids = {did for _, dt, did in task_rows if dt == "world_draft"}
        script_draft_ids = {did for _, dt, did in task_rows if dt == "script_draft"}
        draft_name: dict[str, str] = {}
        if world_draft_ids:
            for did, payload in (
                await db.execute(
                    select(WorldDraft.id, WorldDraft.payload).where(WorldDraft.id.in_(world_draft_ids))
                )
            ).all():
                draft_name[did] = (payload or {}).get("name") or ""
        if script_draft_ids:
            for did, payload in (
                await db.execute(
                    select(ScriptDraft.id, ScriptDraft.payload).where(ScriptDraft.id.in_(script_draft_ids))
                )
            ).all():
                draft_name[did] = (payload or {}).get("name") or ""
        task_name = {tid: draft_name[did] for tid, _, did in task_rows if draft_name.get(did)}

    for it in items:
        rid = it["ref_id"]
        if it["ref_type"] == "session" and rid in sess_map:
            mode, world_name, script_name = sess_map[rid]
            it["ref_title"] = world_name
            it["ref_mode"] = mode
            it["ref_subtitle"] = script_name if mode == "script" else None
            it["ref_turn"] = turn_map.get(it["id"])
        elif it["ref_type"] == "task" and rid in task_name:
            it["ref_title"] = task_name[rid]


@router.get("/balance")
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wallet = await credit_service.get_or_create_wallet(db, current_user.id)
    return {
        "code": 0,
        "data": {
            "balance": units_to_credits(wallet.balance_units),
            "lifetime_granted": units_to_credits(wallet.lifetime_granted_units),
            "lifetime_spent": units_to_credits(wallet.lifetime_spent_units),
        },
        "message": "ok",
    }


@router.get("/transactions")
async def list_transactions(
    limit: int = 30,
    before: str | None = None,
    session: str | None = None,
    category: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(int(limit), 100))
    stmt = select(CreditLedger).where(CreditLedger.user_id == current_user.id)
    categories = _parse_category_filter(category)
    if categories is not None:
        stmt = stmt.where(CreditLedger.category.in_(categories) if categories else false())
    # 本局流水：play 页「本局积分」抽屉用，只回该 session 关联的扣费行。
    if session:
        stmt = stmt.where(
            CreditLedger.ref_type == "session",
            CreditLedger.ref_id == session,
        )
    if before:
        try:
            stmt = stmt.where(CreditLedger.created_at < datetime.fromisoformat(before))
        except ValueError:
            pass
    stmt = stmt.order_by(CreditLedger.created_at.desc()).limit(limit + 1)
    rows = (await db.execute(stmt)).scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        {
            "id": r.id,
            # created_at 是 naive UTC；显式标 UTC，前端 new Date() 才会转对本地时区。
            "ts": r.created_at.replace(tzinfo=timezone.utc).isoformat(),
            "kind": r.kind,
            "category": r.category,
            "delta": units_to_credits(r.delta_units),
            "balance_after": units_to_credits(r.balance_after_units),
            "note": r.note,
            "ref_type": r.ref_type,
            "ref_id": r.ref_id,
            "ref_title": None,
            "ref_subtitle": None,
            "ref_mode": None,
            "ref_turn": None,
        }
        for r in rows
    ]
    await _enrich_refs(db, current_user.id, items)
    next_cursor = rows[-1].created_at.isoformat() if (has_more and rows) else None
    return {"code": 0, "data": {"items": items, "next_cursor": next_cursor}, "message": "ok"}
