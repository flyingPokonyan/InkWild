import asyncio
import json
from inspect import isawaitable

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from config import settings
from dependencies import get_current_user, get_db, get_redis
from engine.case_board_prompts import derive_progress_phase
from engine.orchestrator import Orchestrator
from llm.deepseek import DeepSeekProvider
from llm.router import LLMRouter
from middleware.rate_limit import RedisTokenBucketRateLimiter
from middleware.error_handler import AppError
from models.case_board_history import CaseBoardHistory
from models.game import GameSession
from models.script import Script
from models.user import User
from models.world import World, WorldCharacter
from schemas.game import CaseBoardHistoryItem, CaseBoardResponse, GameActionRequest, GameHistoryItem, GameStartRequest
from database import async_session
from llm.usage_context import usage_accumulator
from services import credit_service
from services.game_service import GameService
from services.model_management import resolve_slot_router
from services.session_lock import SessionLock

router = APIRouter(prefix="/api/game", tags=["game"])
logger = structlog.get_logger()

# SSE heartbeat interval. sse-starlette emits a comment line (": ping ...")
# every N seconds when the upstream generator is idle. Browsers/proxies treat
# comment lines as keepalive only — they never reach the EventSource onmessage
# path. The frontend uses these to keep `lastDataTimestamp` fresh and detect
# real connection loss after 90s of total silence.
SSE_PING_INTERVAL_SECONDS = 30

# Categories for SSE error events. Mirrored on the frontend as `SSEErrorCode`.
SSE_ERROR_CODE_RATE_LIMIT = "rate_limit"
SSE_ERROR_CODE_COST_CAP = "cost_cap"
SSE_ERROR_CODE_LLM_TIMEOUT = "llm_timeout"
SSE_ERROR_CODE_PROVIDER_DOWN = "provider_down"
SSE_ERROR_CODE_MODERATION = "moderation"
# Phase 2.A.3 — LLM responded but produced no usable structured output.
# Distinct from `provider_down` so the UI can offer a "retry round" button
# (the provider is alive; we just got an unparseable response).
SSE_ERROR_CODE_LLM_PARSE = "llm_parse"
SSE_ERROR_CODE_UNKNOWN = "unknown"
# Phase 1 credits — balance can't cover the action's estimate (L2 gate).
SSE_ERROR_CODE_CREDITS = "credits_insufficient"

# AppError numeric codes that already represent moderation rejections.
_MODERATION_LEGACY_CODES = {40001}

# AppError numeric codes that map to provider-side issues. Most AppError codes
# are user-facing validation errors that never enter the SSE stream proper, so
# we only translate the ones that can plausibly reach the SSE pipeline at runtime.
_PROVIDER_DOWN_LEGACY_CODES = {50001}


def _classify_legacy_app_error(legacy_code: int) -> str:
    """Map an AppError numeric code to one of the SSE error categories."""

    if legacy_code in _MODERATION_LEGACY_CODES:
        return SSE_ERROR_CODE_MODERATION
    if legacy_code in _PROVIDER_DOWN_LEGACY_CODES:
        return SSE_ERROR_CODE_PROVIDER_DOWN
    return SSE_ERROR_CODE_UNKNOWN


def _classify_runtime_exception(exc: Exception) -> tuple[str, str]:
    """Map a runtime exception raised inside the SSE generator to (code, message)."""

    # asyncio.TimeoutError aliases to TimeoutError in 3.11+, but tolerate either.
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return SSE_ERROR_CODE_LLM_TIMEOUT, "LLM 调用超时，请稍后重试"

    # Connection / network errors from httpx, aiohttp, urllib, etc.
    exc_name = type(exc).__name__.lower()
    if "connect" in exc_name or "network" in exc_name or "httperror" in exc_name:
        return SSE_ERROR_CODE_PROVIDER_DOWN, "LLM 服务暂时不可用，请稍后重试"

    return SSE_ERROR_CODE_UNKNOWN, "LLM 服务暂时不可用，请稍后重试"


def _legacy_game_router() -> LLMRouter:
    provider = DeepSeekProvider()
    return LLMRouter(
        providers={settings.llm_provider: provider},
        fallback_chain=[settings.llm_provider],
        identity={
            "provider_name": f"{settings.llm_provider}-legacy",
            "model_id": getattr(provider, "model", None) or settings.llm_default_model,
        },
    )


def _game_key_affinity(*, world_id: str, script_id: str | None, mode: str) -> str:
    """Cache-domain affinity for provider key selection.

    Keep this intentionally coarse: all players in the same world/script/mode
    prefer the same API key, maximizing upstream prefix-cache reuse.
    """

    return f"game:{mode}:world:{world_id}:script:{script_id or 'none'}"


async def _session_key_affinity(db: AsyncSession, *, user_id: str, session_id: str) -> str:
    row = (
        await db.execute(
            select(GameSession.world_id, GameSession.script_id, GameSession.mode)
            .where(GameSession.id == session_id, GameSession.user_id == user_id)
        )
    ).one_or_none()
    if row is None:
        return f"game:session:{session_id}"
    world_id, script_id, mode = row
    return _game_key_affinity(world_id=str(world_id), script_id=str(script_id) if script_id else None, mode=mode)


async def get_game_service(db: AsyncSession, *, key_affinity: str | None = None) -> GameService:
    game_router = await resolve_slot_router(db, "game_main", key_affinity=key_affinity) or _legacy_game_router()
    compression_router = await resolve_slot_router(
        db, "conversation_compression", key_affinity=key_affinity
    ) or game_router
    ending_summary_router = await resolve_slot_router(db, "ending_summary", key_affinity=key_affinity) or game_router
    # Optional cheaper slot for NPC dialogue. Falls back to game_main when unbound.
    npc_router = await resolve_slot_router(db, "npc_agent", key_affinity=key_affinity) or game_router
    orchestrator = Orchestrator(
        llm_router=game_router,
        compression_llm_router=compression_router,
        ending_summary_llm_router=ending_summary_router,
        npc_llm_router=npc_router,
    )
    return GameService(orchestrator=orchestrator)


async def _resolve_game_service(db: AsyncSession, *, key_affinity: str | None = None) -> GameService:
    try:
        service = get_game_service(db, key_affinity=key_affinity)
    except TypeError:
        try:
            service = get_game_service(db)
        except TypeError:
            service = get_game_service()
    if isawaitable(service):
        return await service
    return service


def to_sse_event(event: dict) -> dict:
    event_type = event["type"]
    if event_type == "state_ready":
        raise ValueError("state_ready is an internal event and must not be serialized")

    client_event = {"type": event_type, "version": 1}

    if event_type == "session_created" and "session_id" in event:
        client_event["session_id"] = event["session_id"]
    elif event_type == "processing":
        if "phase" in event:
            client_event["phase"] = event["phase"]
        if "focus_npcs" in event:
            client_event["focus_npcs"] = event["focus_npcs"]
        if "flavor" in event:
            client_event["flavor"] = event["flavor"]
        if "kind" in event:
            client_event["kind"] = event["kind"]
        # 思考态演进进度（stage 驱动，文案在前端按 i18n 拼装）
        if "stage" in event:
            client_event["stage"] = event["stage"]
        if "input_summary" in event:
            client_event["input_summary"] = event["input_summary"]
        if "npcs" in event:
            client_event["npcs"] = event["npcs"]
    elif event_type == "case_board_update":
        # Phase-4 follow-up — case board refreshes a beat after `done`.
        if "game_state" in event:
            client_event["game_state"] = event["game_state"]
    elif event_type == "narrative" and "text" in event:
        client_event["text"] = event["text"]
    elif event_type == "state_update":
        if "game_state" in event:
            client_event["game_state"] = event["game_state"]
        if "quick_actions" in event:
            client_event["quick_actions"] = event["quick_actions"]
        if "triggered_events" in event:
            client_event["triggered_events"] = event["triggered_events"]
    elif event_type == "ending":
        if "ending_type" in event:
            client_event["ending_type"] = event["ending_type"]
        if "title" in event:
            client_event["title"] = event["title"]
        if "summary" in event:
            client_event["summary"] = event["summary"]
    elif event_type == "error":
        # `code` is a string enum on the wire (rate_limit / cost_cap / llm_timeout /
        # provider_down / moderation / unknown). Internal callers may pass either:
        #   - {"code": "<string>", "legacy_code": <int>}  — preferred new shape
        #   - {"code": <int>}                              — legacy AppError numeric code
        # The numeric form is auto-classified into the string enum and preserved
        # under `legacy_code` so admin/log consumers keep their existing data.
        raw_code = event.get("code")
        if isinstance(raw_code, str):
            client_event["code"] = raw_code
            if "legacy_code" in event:
                client_event["legacy_code"] = event["legacy_code"]
        elif isinstance(raw_code, int):
            client_event["code"] = _classify_legacy_app_error(raw_code)
            client_event["legacy_code"] = raw_code
        else:
            client_event["code"] = SSE_ERROR_CODE_UNKNOWN
        if "retry_after_ms" in event:
            client_event["retry_after_ms"] = event["retry_after_ms"]
        if "message" in event:
            client_event["message"] = event["message"]
    elif event_type in ("cost_warning", "cap_reached"):
        if "message" in event:
            client_event["message"] = event["message"]
        if "suggest" in event:
            client_event["suggest"] = event["suggest"]
        if "total_cost_cents" in event:
            client_event["total_cost_cents"] = event["total_cost_cents"]
        if "cap_cost_cents" in event:
            client_event["cap_cost_cents"] = event["cap_cost_cents"]

    return {"event": event_type, "data": json.dumps(client_event, ensure_ascii=False)}


def to_error_events(exc: Exception) -> list[dict]:
    if isinstance(exc, AppError):
        # AppError carries a numeric code; to_sse_event will classify it into
        # one of the SSE error code buckets and preserve the numeric value as
        # `legacy_code` for any consumer (logs, admin) that still cares.
        return [
            to_sse_event({"type": "error", "code": exc.code, "message": exc.message}),
            to_sse_event({"type": "done"}),
        ]

    logger.warning("game_stream_failed", error=str(exc), exc_info=True)
    code, message = _classify_runtime_exception(exc)
    return [
        to_sse_event({"type": "error", "code": code, "message": message}),
        to_sse_event({"type": "done"}),
    ]


async def _gate_blocks_on_error() -> bool:
    """On a credit-subsystem error, honor ``gate_fail_mode`` (default open)."""
    try:
        async with async_session() as cdb:
            config = await credit_service.get_config(cdb)
            return config.gate_fail_mode == "safe"
    except Exception:  # noqa: BLE001 — fully broken => fail open
        return False


async def _stream_with_credits(user_id: str, *, action: str, session_id: str | None, raw_agen):
    """Wrap a game-turn event stream with the L3 reserve + post-settle.

    Reserve and settle use their own DB sessions so credits stay decoupled from
    the gameplay transaction (and survive a turn that errors). A subsystem
    hiccup follows ``gate_fail_mode`` (default open); a crash between reserve and
    settle leaves a hold the sweep recovers.
    """
    hold_id: str | None = None
    blocked = False
    try:
        async with async_session() as cdb:
            hold_id = await credit_service.reserve(
                cdb, user_id, action=action, ref_type="session", ref_id=session_id
            )
    except credit_service.InsufficientCredits:
        blocked = True
    except Exception:  # noqa: BLE001
        blocked = await _gate_blocks_on_error()
        logger.warning("credit.gate_failed", exc_info=True)

    if blocked:
        yield to_sse_event(
            {"type": "error", "code": SSE_ERROR_CODE_CREDITS, "message": "积分不足"}
        )
        yield to_sse_event({"type": "done"})
        return

    ref_id = session_id
    saw_content = False
    errored = False
    with usage_accumulator() as acc:
        try:
            async for event in raw_agen:
                etype = event.get("type")
                if etype == "session_created" and not ref_id:
                    ref_id = event.get("session_id")
                if etype == "narrative":
                    saw_content = True
                yield to_sse_event(event)
        except Exception as exc:  # noqa: BLE001
            errored = True
            for err_event in to_error_events(exc):
                yield err_event
        finally:
            if hold_id is not None:
                # delivered = produced narrative, or completed without erroring.
                delivered = saw_content or not errored
                try:
                    async with async_session() as cdb:
                        # ref_id 可能是开局时从 session_created 现抓的（reserve 时还没 session）。
                        await credit_service.settle_hold(
                            cdb, hold_id, acc, delivered=delivered, ref_id=ref_id
                        )
                except Exception:  # noqa: BLE001 — fail open
                    logger.warning("credit.settle_failed", exc_info=True)


@router.post("/start")
async def start_game(
    req: GameStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    key_affinity = _game_key_affinity(world_id=req.world_id, script_id=req.script_id, mode=req.mode)
    service = await _resolve_game_service(db, key_affinity=key_affinity)

    raw = service.start_game(
        db,
        current_user.id,
        req.world_id,
        req.character_id,
        req.mode,
        req.script_id,
        req.authors_note,
        req.force_abandon_session_id,
        is_admin=current_user.is_admin,
        start_stage_id=req.start_stage_id,
    )
    return EventSourceResponse(
        _stream_with_credits(current_user.id, action="game", session_id=None, raw_agen=raw),
        ping=SSE_PING_INTERVAL_SECONDS,
    )


@router.post("/{session_id}/retry")
async def retry_game(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    lock = SessionLock(redis)
    if not await lock.acquire(session_id):
        raise HTTPException(status_code=429, detail={"code": 42901, "message": "请等待上一轮回复完成"})

    key_affinity = await _session_key_affinity(db, user_id=current_user.id, session_id=session_id)
    service = await _resolve_game_service(db, key_affinity=key_affinity)
    raw = service.retry_action(db, current_user.id, session_id)

    async def event_generator():
        try:
            async for sse in _stream_with_credits(
                current_user.id, action="game", session_id=session_id, raw_agen=raw
            ):
                yield sse
        finally:
            await lock.release(session_id)

    return EventSourceResponse(event_generator(), ping=SSE_PING_INTERVAL_SECONDS)


@router.post("/{session_id}/action")
async def game_action(
    session_id: str,
    req: GameActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    rate_limiter = RedisTokenBucketRateLimiter(redis)
    rate_limit = await rate_limiter.allow(
        current_user.id,
        limit=settings.game_action_rate_limit_per_minute,
        window_seconds=settings.game_action_rate_limit_window_seconds,
    )
    if not rate_limit.allowed:
        raise HTTPException(
            status_code=429,
            detail={"code": 42902, "message": "操作过于频繁，请稍后再试"},
            headers={"Retry-After": str(rate_limit.retry_after_seconds or 1)},
        )

    lock = SessionLock(redis)
    if not await lock.acquire(session_id):
        raise HTTPException(status_code=429, detail={"code": 42901, "message": "请等待上一轮回复完成"})

    key_affinity = await _session_key_affinity(db, user_id=current_user.id, session_id=session_id)
    service = await _resolve_game_service(db, key_affinity=key_affinity)
    raw = service.process_action(db, current_user.id, session_id, req.action_text)

    async def event_generator():
        try:
            async for sse in _stream_with_credits(
                current_user.id, action="game", session_id=session_id, raw_agen=raw
            ):
                yield sse
        finally:
            await lock.release(session_id)

    return EventSourceResponse(event_generator(), ping=SSE_PING_INTERVAL_SECONDS)


@router.get("/{session_id}/detail")
async def get_game_detail(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _resolve_game_service(db)
    data = await service.get_session_detail(db, session_id, current_user.id)
    return {"code": 0, "data": data}


@router.get("/{session_id}/state")
async def get_game_state(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _resolve_game_service(db)
    return {"code": 0, "data": await service.get_game_state(db, current_user.id, session_id)}


@router.get("/{session_id}/case-board")
async def get_case_board(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(GameSession, session_id)
    if not session or session.user_id != current_user.id:
        raise AppError(40003, "游戏会话不存在", status_code=404)
    if session.mode != "script":
        raise AppError(40004, "案件板仅在剧本模式可用", status_code=404)

    history_result = await db.execute(
        select(CaseBoardHistory)
        .where(CaseBoardHistory.session_id == session.id)
        .order_by(CaseBoardHistory.id.asc())
    )
    history = [
        CaseBoardHistoryItem(
            id=item.id,
            session_id=str(item.session_id),
            round_number=item.round_number,
            op_type=item.op_type,
            path=item.path,
            payload=item.payload,
            before=item.before,
            after=item.after,
            reason=item.reason,
            created_at=item.created_at.isoformat(),
        )
        for item in history_result.scalars().all()
    ]

    game_state = session.game_state or {}
    current = dict(game_state.get("case_board") or {})
    # progress_phase is derived from narrative_arc + script_type so it stays
    # consistent with the canonical act. Strip any legacy Director-written
    # value before injecting the derived label.
    current.pop("progress_phase", None)
    script_type = "mystery"
    if session.script_id:
        script = await db.get(Script, session.script_id)
        if script is not None:
            script_type = getattr(script, "script_type", None) or "mystery"
    current_act = (game_state.get("narrative_arc") or {}).get("current_act", "")
    phase = derive_progress_phase(script_type, current_act)
    if phase:
        current["progress_phase"] = phase

    data = CaseBoardResponse(current=current, history=history)
    return {"code": 0, "data": data.model_dump()}


@router.post("/{session_id}/pause")
async def pause_game(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _resolve_game_service(db)
    await service.pause_game(db, current_user.id, session_id)
    return {"code": 0, "message": "ok"}


@router.post("/{session_id}/abandon")
async def abandon_game(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """玩家主动放弃当前局。status=ended, ending_type=abandoned。"""
    service = await _resolve_game_service(db)
    await service.abandon_game(db, current_user.id, session_id)
    return {"code": 0, "message": "ok"}


@router.post("/{session_id}/resume")
async def resume_game(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    lock = SessionLock(redis)
    if not await lock.acquire(session_id):
        raise HTTPException(status_code=429, detail={"code": 42901, "message": "请等待上一轮回复完成"})

    key_affinity = await _session_key_affinity(db, user_id=current_user.id, session_id=session_id)
    service = await _resolve_game_service(db, key_affinity=key_affinity)

    async def event_generator():
        try:
            try:
                async for event in service.resume_game(db, current_user.id, session_id):
                    yield to_sse_event(event)
            except Exception as exc:  # noqa: BLE001
                for event in to_error_events(exc):
                    yield event
        finally:
            await lock.release(session_id)

    return EventSourceResponse(event_generator(), ping=SSE_PING_INTERVAL_SECONDS)


@router.get("/history")
async def game_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GameSession, World, WorldCharacter, Script)
        .join(World, GameSession.world_id == World.id)
        .join(WorldCharacter, GameSession.character_id == WorldCharacter.id)
        .outerjoin(Script, GameSession.script_id == Script.id)
        .where(GameSession.user_id == current_user.id)
        .order_by(GameSession.last_played_at.desc())
    )

    items = [
        GameHistoryItem(
            session_id=str(session.id),
            world_id=str(session.world_id),
            script_id=str(session.script_id) if session.script_id else None,
            character_id=str(session.character_id),
            world_name=world.name,
            script_name=script.name if script else None,
            script_cover_image=script.cover_image if script else None,
            character_name=character.name,
            status=session.status,
            ending_type=session.ending_type,
            started_at=session.started_at.isoformat(),
            last_played_at=session.last_played_at.isoformat(),
            cover_image=world.cover_image,
            rounds_played=session.rounds_played,
            current_time=session.game_state.get("current_time") if session.game_state else None,
            current_location=session.game_state.get("current_location") if session.game_state else None,
            mode=session.mode,
            genre=world.genre,
            era=world.era,
        ).model_dump()
        for session, world, character, script in result.all()
    ]
    return {"code": 0, "data": items}
