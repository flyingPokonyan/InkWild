from __future__ import annotations

import asyncio
import json
import inspect

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import async_session
from dependencies import get_current_admin_user, get_db
from llm.deepseek import DeepSeekProvider
from llm.router import LLMRouter
from models.draft import ScriptDraft, WorldDraft
from models.generation_task import GenerationTask, GenerationTaskEvent
from models.world_quality_score import WorldQualityScore
from models.script import Script
from models.user import User
from models.world import World, WorldCharacter
from services.generation_task_service import (
    GenerationTaskLimitExceeded,
    GenerationTaskService,
)
from services.model_management import (
    resolve_research_web_searcher,
    resolve_slot_image_generator,
    resolve_slot_provider,
    resolve_slot_router,
)
from services.world_image_fields import resolve_world_image_fields_from_model
from services.tavily_search import TavilySearch
from services.world_creator_agent import WorldCreatorAgent
from services.publish_service import (
    LOCATION_BLOCK_HEADER as _LOCATION_BLOCK_HEADER,
    normalize_world_payload as _normalize_world_payload,
    normalize_script_payload as _normalize_script_payload,
    _split_world_setting,
)
from utils import serialize_utc_datetime

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_current_admin_user)])

LOCATION_BLOCK_HEADER = _LOCATION_BLOCK_HEADER
_generation_task_limit_locks: dict[str, asyncio.Lock] = {}


async def verify_admin(current_admin_user: User = Depends(get_current_admin_user)) -> User:
    return current_admin_user


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _generation_task_limit_error(exc: GenerationTaskLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "GENERATION_TASK_LIMIT_EXCEEDED",
            "message": "当前管理员已有 2 个生成任务在运行，请稍后再试",
            "limit": exc.limit,
            "active_count": exc.active_count,
        },
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


def _generation_task_limit_lock(admin_user: User) -> asyncio.Lock:
    admin_user_id = str(admin_user.id)
    lock = _generation_task_limit_locks.get(admin_user_id)
    if lock is None:
        lock = asyncio.Lock()
        _generation_task_limit_locks[admin_user_id] = lock
    return lock


def _get_llm_router() -> LLMRouter:
    provider = DeepSeekProvider()
    return LLMRouter(
        providers={settings.llm_provider: provider},
        fallback_chain=[settings.llm_provider],
    )


async def _get_world_creator_agent(db: AsyncSession) -> WorldCreatorAgent:
    llm_router = await resolve_slot_router(db, "admin_generation") or _get_llm_router()
    search_plan_llm = await resolve_slot_router(db, "research_planning") or llm_router
    tavily = TavilySearch() if settings.tavily_api_key else None
    research_summarizer = await resolve_slot_provider(db, "research_summary")
    web_searcher = await resolve_research_web_searcher(db)
    image_gen = await resolve_slot_image_generator(db, "image_generation")
    return WorldCreatorAgent(
        llm_router=llm_router,
        search_plan_llm=search_plan_llm,
        tavily=tavily,
        research_summarizer=research_summarizer,
        web_searcher=web_searcher,
        image_generator=image_gen,
    )


_generation_task_service: GenerationTaskService | None = None


def _get_generation_task_service() -> GenerationTaskService:
    global _generation_task_service
    if _generation_task_service is None:
        _generation_task_service = GenerationTaskService(
            session_factory=async_session,
            world_creator_factory=_build_generation_world_creator_agent,
            normalize_world_payload=_normalize_world_payload,
            normalize_script_payload=_normalize_script_payload,
        )
    return _generation_task_service


async def _build_generation_world_creator_agent() -> WorldCreatorAgent:
    async with async_session() as session:
        return await _resolve_world_creator_agent(session)


async def _resolve_world_creator_agent(db: AsyncSession) -> WorldCreatorAgent:
    try:
        agent = _get_world_creator_agent(db)
    except TypeError:
        agent = _get_world_creator_agent()  # type: ignore[call-arg]
    if inspect.isawaitable(agent):
        agent = await agent
    return agent


def to_sse_event(event: str, payload: dict) -> dict:
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False)}


def _stream_generation_event(event: dict) -> dict:
    return to_sse_event(event["type"], {key: value for key, value in event.items() if key != "type"})


def _world_payload_from_models(world: World, world_chars: list[WorldCharacter]) -> dict:
    base_setting, locations = _split_world_setting(world.base_setting, world.locations_data or [])
    images = resolve_world_image_fields_from_model(world)
    return {
        "name": world.name,
        "description": world.description,
        "genre": world.genre,
        "era": world.era,
        "difficulty": world.difficulty,
        "estimated_time": world.estimated_time,
        "base_setting": base_setting,
        "free_setting": world.free_setting or "",
        "cover_image": images["cover_image"],
        "hero_image": images["hero_image"],
        "locations": locations,
        "world_characters": [
            {
                "name": wc.name,
                "personality": wc.personality,
                "secret": wc.secret,
                "knowledge": wc.knowledge or [],
                "schedule": wc.schedule or {},
                "initial_location": wc.initial_location,
                "playable": wc.playable,
                "description": wc.description,
                "abilities": wc.abilities or [],
                "starting_inventory": wc.starting_inventory or [],
                "avatar": wc.avatar or "",
                "initial_peer_relations": wc.initial_peer_relations or [],
            }
            for wc in world_chars
        ],
    }


def _script_payload_from_model(script: Script) -> dict:
    return {
        "name": script.name,
        "description": script.description,
        "difficulty": script.difficulty,
        "estimated_time": script.estimated_time,
        "script_setting": script.script_setting,
        "events": script.events_data or [],
        "clues": script.clues_data or {},
        "endings": script.endings_data or [],
        "cover_image": script.cover_image or "",
        "playable_character_ids": [str(cid) for cid in (script.playable_character_ids or [])],
    }


def _script_reference_summary_from_model(script: Script) -> dict:
    event_names: list[str] = []
    for event in script.events_data or []:
        if not isinstance(event, dict):
            continue
        name = str(event.get("name", "")).strip()
        if name and name not in event_names:
            event_names.append(name)
        if len(event_names) >= 4:
            break

    ending_types: list[str] = []
    for ending in script.endings_data or []:
        if not isinstance(ending, dict):
            continue
        ending_type = str(ending.get("ending_type", "")).strip()
        if ending_type and ending_type not in ending_types:
            ending_types.append(ending_type)

    return {
        "name": script.name,
        "description": script.description,
        "script_setting": script.script_setting,
        "event_names": event_names,
        "ending_types": ending_types,
    }


def _serialize_generation_task(task: GenerationTask | None, events: list[GenerationTaskEvent] | None = None) -> dict | None:
    if not task:
        return None
    return {
        "id": str(task.id),
        "kind": task.kind,
        "draft_type": task.draft_type,
        "draft_id": str(task.draft_id),
        "status": task.status,
        "current_phase": task.current_phase,
        "current_code": task.current_code,
        "current_message": task.current_message,
        "last_event_seq": task.last_event_seq,
        "error_message": task.error_message,
        "started_at": serialize_utc_datetime(task.started_at),
        "finished_at": serialize_utc_datetime(task.finished_at),
        "created_at": serialize_utc_datetime(task.created_at),
        "updated_at": serialize_utc_datetime(task.updated_at),
        "events": [
            {
                "id": str(event.id),
                "seq": event.seq,
                "event": event.event_name,
                "payload": event.payload,
            }
            for event in (events or [])
        ],
    }


async def _load_latest_generation_task(
    db: AsyncSession,
    *,
    draft_type: str,
    draft_id: str,
) -> tuple[GenerationTask | None, list[GenerationTaskEvent]]:
    task = (
        await db.execute(
            select(GenerationTask)
            .where(GenerationTask.draft_type == draft_type, GenerationTask.draft_id == draft_id)
            .order_by(GenerationTask.created_at.desc())
        )
    ).scalars().first()
    if not task:
        return None, []
    events = (
        await db.execute(
            select(GenerationTaskEvent)
            .where(GenerationTaskEvent.task_id == task.id)
            .order_by(GenerationTaskEvent.seq.asc())
        )
    ).scalars().all()
    return task, list(events)


def _extract_generated_name(task: GenerationTask) -> str | None:
    """Pull the final generated name (world or script) out of a task.

    For world tasks the name lands in intermediate_state.world_base.name after
    Stage B; for script tasks it lands in intermediate_state.script.script_base.name
    after the script_base stage. Tasks that haven't reached that stage yet
    return None — caller decides UI fallback.
    """
    state = task.intermediate_state or {}
    if not isinstance(state, dict):
        return None
    if task.kind == "world":
        wb = state.get("world_base")
        if isinstance(wb, dict):
            name = wb.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    elif task.kind == "script":
        # script intermediate_state stores keys like "script.script_base"
        sb = state.get("script.script_base") or state.get("script_base")
        if isinstance(sb, dict):
            name = sb.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _world_draft_detail(
    draft: WorldDraft,
    *,
    generation_task: GenerationTask | None = None,
    generation_events: list[GenerationTaskEvent] | None = None,
) -> dict:
    return {
        "id": str(draft.id),
        "world_id": str(draft.world_id) if draft.world_id else None,
        "payload": draft.payload,
        "updated_at": serialize_utc_datetime(draft.updated_at),
        "created_at": serialize_utc_datetime(draft.created_at),
        "generation_task": _serialize_generation_task(generation_task, generation_events),
    }


def _script_draft_detail(
    draft: ScriptDraft,
    *,
    generation_task: GenerationTask | None = None,
    generation_events: list[GenerationTaskEvent] | None = None,
) -> dict:
    return {
        "id": str(draft.id),
        "world_id": str(draft.world_id),
        "script_id": str(draft.script_id) if draft.script_id else None,
        "payload": draft.payload,
        "updated_at": serialize_utc_datetime(draft.updated_at),
        "created_at": serialize_utc_datetime(draft.created_at),
        "generation_task": _serialize_generation_task(generation_task, generation_events),
    }



class GenerateWorldRequest(BaseModel):
    description: str
    genre: str = ""
    era: str = ""


class GenerateScriptRequest(BaseModel):
    world_id: str
    outline: str = ""


class CreateWorldGenerationTaskRequest(BaseModel):
    description: str
    genre: str = ""
    era: str = ""


class CreateScriptGenerationTaskRequest(BaseModel):
    world_id: str
    outline: str = ""


class SaveWorldRequest(BaseModel):
    world_data: dict


class SaveScriptRequest(BaseModel):
    world_id: str
    script_data: dict


class CreateWorldDraftRequest(BaseModel):
    world_id: str | None = None
    payload: dict | None = None


class UpdateWorldDraftRequest(BaseModel):
    payload: dict


class CreateScriptDraftRequest(BaseModel):
    world_id: str | None = None
    script_id: str | None = None
    payload: dict | None = None


class UpdateScriptDraftRequest(BaseModel):
    payload: dict


@router.get("/generation-tasks/{task_id}/stream")
async def stream_generation_task(task_id: str, after_seq: int = Query(default=0)):
    service = _get_generation_task_service()

    async def event_generator():
        async for item in service.stream_task_events(task_id, after_seq=after_seq):
            yield to_sse_event(item["event"], item["payload"])

    return EventSourceResponse(event_generator(), ping=15)


@router.get("/generation-tasks")
async def list_generation_tasks(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    include_ip_recognition: bool = Query(default=False),
):
    """List generation tasks for admin (world / script). Supports kind + status filters.

    By default hides the phase_a (IP recognition only) sub-tasks that pair with
    each real world generation — they finish in seconds and only pollute the
    history view. Pass include_ip_recognition=true to surface them.
    """
    from sqlalchemy import func as _sql_func

    base = select(GenerationTask)
    count_q = select(_sql_func.count()).select_from(GenerationTask)
    if kind in ("world", "script"):
        base = base.where(GenerationTask.kind == kind)
        count_q = count_q.where(GenerationTask.kind == kind)
    if status in ("pending", "running", "succeeded", "failed", "cancelled"):
        base = base.where(GenerationTask.status == status)
        count_q = count_q.where(GenerationTask.status == status)
    if not include_ip_recognition:
        # phase_a tasks store {"phase": "phase_a", ...} in request_payload.
        # request_payload is declared JSON (not JSONB); cast inline to access
        # the ->>'phase' operator. Postgres-only — fine for our deployment.
        from sqlalchemy.dialects.postgresql import JSONB as _PgJSONB
        # IS DISTINCT FROM（非 !=）：phase 字段缺失时 ->>'phase' 是 NULL，
        # `NULL != 'phase_a'` 求值为 NULL→当 FALSE 被误过滤，会把没标 phase 的
        # 正常世界生成一起藏掉。IS DISTINCT FROM 把 NULL 当作"不等于"正确放行。
        phase_a_filter = (
            GenerationTask.request_payload.cast(_PgJSONB)["phase"].astext.is_distinct_from("phase_a")
        )
        base = base.where(phase_a_filter)
        count_q = count_q.where(phase_a_filter)

    total = (await db.execute(count_q)).scalar_one() or 0
    rows = (
        await db.execute(
            base.order_by(GenerationTask.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).scalars().all()

    # 批量取这一页 task 的质量分（异步打分产物），列表展示 overall + must_have/backfill 快览。
    task_ids = [str(t.id) for t in rows]
    score_map: dict[str, WorldQualityScore] = {}
    if task_ids:
        score_rows = (
            await db.execute(
                select(WorldQualityScore).where(WorldQualityScore.task_id.in_(task_ids))
            )
        ).scalars().all()
        for sr in score_rows:
            score_map[str(sr.task_id)] = sr

    items: list[dict] = []
    for t in rows:
        req = t.request_payload or {}
        sr = score_map.get(str(t.id))
        items.append({
            "id": str(t.id),
            "kind": t.kind,
            "draft_type": t.draft_type,
            "draft_id": str(t.draft_id) if t.draft_id else None,
            "status": t.status,
            "current_phase": t.current_phase,
            "current_message": t.current_message,
            "last_event_seq": t.last_event_seq,
            "error_message": t.error_message,
            "prompt_preview": (req.get("description") or req.get("outline") or "")[:120],
            "fidelity_mode": req.get("fidelity_mode"),
            "ip_name": (req.get("ip_recognition") or req.get("pre_recognition") or {}).get("ip_name"),
            "generated_name": _extract_generated_name(t),
            "quality_score": sr.overall_score if sr else None,
            "quality_backfill": sr.backfill_count if sr else None,
            "quality_must_have": (f"{sr.must_have_covered}/{sr.must_have_total}" if sr and sr.must_have_total else None),
            "created_at": serialize_utc_datetime(t.created_at),
            "started_at": serialize_utc_datetime(t.started_at),
            "finished_at": serialize_utc_datetime(t.finished_at),
        })

    return {"code": 0, "data": {"items": items, "total": total, "page": page, "limit": limit}}


@router.get("/generation-tasks/{task_id}")
async def get_generation_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    """Single generation task detail + full event stream (replayed from DB)."""
    task = await db.get(GenerationTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="generation_task not found")
    events = (
        await db.execute(
            select(GenerationTaskEvent)
            .where(GenerationTaskEvent.task_id == task.id)
            .order_by(GenerationTaskEvent.seq.asc())
        )
    ).scalars().all()
    payload = _serialize_generation_task(task, list(events))
    if payload is not None:
        req = task.request_payload or {}
        payload["request_payload"] = req
        payload["prompt_preview"] = (req.get("description") or req.get("outline") or "")[:120]
        payload["fidelity_mode"] = req.get("fidelity_mode")
        payload["ip_name"] = (req.get("ip_recognition") or req.get("pre_recognition") or {}).get("ip_name")
        payload["generated_name"] = _extract_generated_name(task)

        # Find the companion task (same draft_id, opposite phase) so the detail
        # view can show Stage 0 IP recognition as a prelude to the main build.
        companion = None
        if task.draft_id:
            comp_row = (
                await db.execute(
                    select(GenerationTask)
                    .where(
                        GenerationTask.draft_id == task.draft_id,
                        GenerationTask.id != task.id,
                    )
                    .order_by(GenerationTask.created_at.asc())
                    .limit(1)
                )
            ).scalars().first()
            if comp_row is not None:
                comp_events = (
                    await db.execute(
                        select(GenerationTaskEvent)
                        .where(GenerationTaskEvent.task_id == comp_row.id)
                        .order_by(GenerationTaskEvent.seq.asc())
                    )
                ).scalars().all()
                companion = _serialize_generation_task(comp_row, list(comp_events))
                if companion is not None:
                    comp_req = comp_row.request_payload or {}
                    companion["phase_kind"] = comp_req.get("phase")  # phase_a / phase_b
        payload["companion_task"] = companion
        payload["phase_kind"] = req.get("phase")

        # 质量报告（异步打分产物）。可能尚未落表（打分比 done 晚几秒）→ None。
        qs = (
            await db.execute(
                select(WorldQualityScore)
                .where(WorldQualityScore.task_id == task.id)
                .order_by(WorldQualityScore.scored_at.desc())
                .limit(1)
            )
        ).scalars().first()
        payload["quality"] = _serialize_quality(qs) if qs else None
    return {"code": 0, "data": payload}


def _serialize_quality(qs: WorldQualityScore) -> dict:
    """质量报告序列化：硬指标(客观) / 软分(LLM,仅参考) / 安全网触发量 分区。"""
    return {
        "overall_score": qs.overall_score,
        "hard": {
            "character_count": qs.character_count,
            "playable_count": qs.playable_count,
            "must_have_covered": qs.must_have_covered,
            "must_have_total": qs.must_have_total,
            "events_count": qs.events_count,
            "shared_events_count": qs.shared_events_count,
            "structure_score": qs.structure_score,
        },
        "soft": {
            "ip_consistency": qs.soft_ip_consistency,
            "collision": qs.soft_collision,
            "tension": qs.soft_tension,
            "summary": qs.soft_summary,
        },
        "safety_net": {
            "backfill_count": qs.backfill_count,
            "prune_count": qs.prune_count,
            "soft_warning_count": qs.soft_warning_count,
        },
        "scored_at": serialize_utc_datetime(qs.scored_at),
    }
