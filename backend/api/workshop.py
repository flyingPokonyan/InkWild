"""User-facing creation workshop routes.

Mirrors the creation-related subset of /api/admin/* with:
- get_current_user (not get_current_admin_user)
- ownership filter (users see only their own drafts/tasks)
- _require_can_create() gate
- daily quota checks via services.quota_service
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from config import settings
from database import async_session
from dependencies import get_current_user, get_db
from models.draft import ScriptDraft, WorldDraft
from models.generation_task import GenerationTask, GenerationTaskEvent
from models.script import Script
from models.user import User
from models.world import World, WorldCharacter
from schemas.ip_knowledge_pack import FidelityMode
from services.generation_task_service import (
    GenerationTaskLimitExceeded,
    GenerationTaskService,
    PHASE_A,
    PHASE_B,
)
from services.model_management import (
    resolve_research_web_searcher,
    resolve_slot_image_generator,
    resolve_slot_provider,
    resolve_slot_router,
)
from services import publish_service
from services.image_regeneration import (
    ImageRegenerationError,
    build_script_draft_image_prompt,
    build_world_draft_image_prompt,
    regenerate_script_draft_image,
    regenerate_world_draft_image,
)
from services.image_storage import IMAGE_PLACEHOLDER_URL, get_image_storage, make_image_key
from services.quota_service import QuotaExceeded, consume_world_generation_quota, consume_script_generation_quota
from services.publish_service import (
    normalize_world_payload as _normalize_world_payload,
    normalize_script_payload as _normalize_script_payload,
)
from api.admin import (  # noqa: E402  (after services to avoid circular at module load)
    _world_payload_from_models,
    _script_payload_from_model,
)
from services.tavily_search import TavilySearch
from services.world_creator_agent import WorldCreatorAgent
from services.world_image_fields import (
    resolve_world_image_fields_from_mapping,
    resolve_world_image_fields_from_model,
)
from utils import serialize_utc_datetime
from llm.deepseek import DeepSeekProvider
from llm.router import LLMRouter
from llm.usage_context import usage_context
import inspect

router = APIRouter(prefix="/api/workshop", tags=["workshop"])

# ---------------------------------------------------------------------------
# Auth / permission helpers
# ---------------------------------------------------------------------------


def _require_can_create(user: User) -> None:
    if not (user.can_create or user.is_admin):
        raise HTTPException(
            status_code=403,
            detail={"code": 40300, "message": "Not in creator whitelist"},
        )


def _ownership_filter(query, model_cls, user: User):
    """Add WHERE created_by_user_id = user.id unless admin (admin sees all)."""
    if user.is_admin:
        return query
    return query.where(model_cls.created_by_user_id == user.id)


def _prefer_draft_image(draft_image: str, current_image: str) -> str:
    draft_image = (draft_image or "").strip()
    if not draft_image or draft_image == IMAGE_PLACEHOLDER_URL:
        return current_image
    return draft_image


def _existing_workshop_image_url(url: str) -> str:
    url = (url or "").strip()
    if not url or url == IMAGE_PLACEHOLDER_URL:
        return ""
    static_prefix = "/static/images/"
    if url.startswith(static_prefix):
        relative_path = unquote(url[len(static_prefix):]).lstrip("/")
        if not (Path(settings.image_storage_dir) / relative_path).is_file():
            return ""
    return url


def _normalize_workshop_image_fields(images: dict[str, str]) -> dict[str, str]:
    cover = _existing_workshop_image_url(images["cover_image"])
    hero = _existing_workshop_image_url(images["hero_image"])
    if not cover:
        cover = hero
    if not hero:
        hero = cover
    return {"cover_image": cover, "hero_image": hero}


def _world_payload_for_response(payload: dict | None) -> dict:
    data = dict(payload or {})
    images = _normalize_workshop_image_fields(resolve_world_image_fields_from_mapping(data))
    data["cover_image"] = images["cover_image"]
    data["hero_image"] = images["hero_image"]
    return data


def _script_payload_for_response(payload: dict | None) -> dict:
    data = dict(payload or {})
    data["cover_image"] = _existing_workshop_image_url(data.get("cover_image", ""))
    return data


def _assert_owner(obj, user: User, label: str = "resource") -> None:
    """Raise 403 if user is not the owner and not admin."""
    if not user.is_admin and obj.created_by_user_id != str(user.id):
        raise HTTPException(status_code=403, detail=f"Not owner of {label}")


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _to_sse_event(event: str, payload: dict, *, seq: int | None = None) -> dict:
    sse_event = {"event": event, "data": json.dumps(payload, ensure_ascii=False)}
    if seq is not None:
        sse_event["id"] = str(seq)
    return sse_event


# ---------------------------------------------------------------------------
# GenerationTaskService singleton (shared with admin; re-uses same factory)
# ---------------------------------------------------------------------------


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


async def _build_generation_world_creator_agent() -> WorldCreatorAgent:
    async with async_session() as session:
        agent = _get_world_creator_agent(session)
        if inspect.isawaitable(agent):
            agent = await agent
        return agent


_workshop_generation_task_service: GenerationTaskService | None = None


def _get_generation_task_service() -> GenerationTaskService:
    global _workshop_generation_task_service
    if _workshop_generation_task_service is None:
        _workshop_generation_task_service = GenerationTaskService(
            session_factory=async_session,
            world_creator_factory=_build_generation_world_creator_agent,
            normalize_world_payload=_normalize_world_payload,
            normalize_script_payload=_normalize_script_payload,
        )
    return _workshop_generation_task_service


# Per-user lock for concurrent generation task limit check
_workshop_task_limit_locks: dict[str, asyncio.Lock] = {}


def _get_task_limit_lock(user: User) -> asyncio.Lock:
    uid = str(user.id)
    if uid not in _workshop_task_limit_locks:
        _workshop_task_limit_locks[uid] = asyncio.Lock()
    return _workshop_task_limit_locks[uid]


def _generation_task_limit_error(exc: GenerationTaskLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "GENERATION_TASK_LIMIT_EXCEEDED",
            "message": f"当前用户已有 {exc.active_count} 个生成任务在运行（上限 {exc.limit}），请稍后再试",
            "limit": exc.limit,
            "active_count": exc.active_count,
        },
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialize_generation_task(
    task: GenerationTask | None,
    events: list[GenerationTaskEvent] | None = None,
) -> dict | None:
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


def _world_draft_detail(
    draft: WorldDraft,
    *,
    generation_task: GenerationTask | None = None,
    generation_events: list[GenerationTaskEvent] | None = None,
) -> dict:
    return {
        "id": str(draft.id),
        "world_id": str(draft.world_id) if draft.world_id else None,
        "payload": _world_payload_for_response(draft.payload),
        "updated_at": serialize_utc_datetime(draft.updated_at),
        "created_at": serialize_utc_datetime(draft.created_at),
        "generation_task": _serialize_generation_task(generation_task, generation_events),
    }


async def _load_world_playable_characters(db: AsyncSession, world_id: str) -> list[dict]:
    """世界里的可玩角色（id/name/avatar），供脚本编辑器的可玩角色多选用。
    按 narrative_weight 排序，与 get_world 的角色顺序一致。"""
    rows = (
        await db.execute(
            select(WorldCharacter)
            .where(WorldCharacter.world_id == world_id, WorldCharacter.playable.is_(True))
            .order_by(
                WorldCharacter.narrative_weight.desc(),
                WorldCharacter.created_at.asc(),
            )
        )
    ).scalars().all()
    return [{"id": str(c.id), "name": c.name, "avatar": c.avatar} for c in rows]


def _script_draft_detail(
    draft: ScriptDraft,
    *,
    generation_task: GenerationTask | None = None,
    generation_events: list[GenerationTaskEvent] | None = None,
    world_playable_characters: list[dict] | None = None,
) -> dict:
    return {
        "id": str(draft.id),
        "world_id": str(draft.world_id),
        "script_id": str(draft.script_id) if draft.script_id else None,
        "payload": _script_payload_for_response(draft.payload),
        # 该剧本所属世界的全部可玩角色，编辑器据此渲染可玩角色多选清单。
        "world_playable_characters": world_playable_characters or [],
        "updated_at": serialize_utc_datetime(draft.updated_at),
        "created_at": serialize_utc_datetime(draft.created_at),
        "generation_task": _serialize_generation_task(generation_task, generation_events),
    }


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateWorldGenerationTaskRequest(BaseModel):
    description: str
    genre: str = ""
    era: str = ""


class ContinueWorldGenerationRequest(BaseModel):
    fidelity_mode: FidelityMode


class CreateScriptGenerationTaskRequest(BaseModel):
    world_id: str
    outline: str = ""


class ScriptPremiseSuggestionsRequest(BaseModel):
    world_id: str
    count: int = 4


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


# ---------------------------------------------------------------------------
# Image upload + single-image regeneration
# ---------------------------------------------------------------------------

# base64 data URL upload — mirrors the avatar pattern in api/auth.py (JSON, no
# multipart). Covers are bigger than avatars, hence the per-kind size table.
_IMAGE_DATA_URL_RE = re.compile(r"^data:(?P<mime>image/[a-z+]+);base64,(?P<b64>.+)$", re.DOTALL)
_IMAGE_MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_UPLOAD_MAX_BYTES = {"avatar": 2 * 1024 * 1024, "cover": 5 * 1024 * 1024}


class UploadImageRequest(BaseModel):
    # base64 data URL（前端 FileReader.readAsDataURL 直出）。5MB 二进制 ≈ 6.7MB base64。
    image: str = Field(min_length=1, max_length=8_000_000)
    kind: Literal["avatar", "cover"] = "cover"


class RegenerateWorldImageRequest(BaseModel):
    # "hero" | "cover" | "avatar:<角色名>"
    target: str = Field(min_length=1, max_length=120)
    hint: str = Field(default="", max_length=500)
    prompt: str | None = Field(default=None, max_length=12000)


class RegenerateScriptImageRequest(BaseModel):
    target: Literal["cover"] = "cover"
    hint: str = Field(default="", max_length=500)
    prompt: str | None = Field(default=None, max_length=12000)


class WorldImagePromptRequest(BaseModel):
    # "hero" | "cover" | "avatar:<角色名>"
    target: str = Field(min_length=1, max_length=120)


class ScriptImagePromptRequest(BaseModel):
    target: Literal["cover"] = "cover"


def _persist_world_draft_image_url(draft: WorldDraft, *, target: str, url: str) -> None:
    payload = dict(draft.payload or {})
    if target == "hero":
        payload["hero_image"] = url
    elif target == "cover":
        payload["cover_image"] = url
    elif target.startswith("avatar:"):
        character_name = target.removeprefix("avatar:").strip()
        if not character_name:
            return
        character_images = payload.get("character_images") or {}
        if not isinstance(character_images, dict):
            character_images = {}
        character_images = dict(character_images)
        character_images[character_name] = url
        payload["character_images"] = character_images

        characters = []
        for item in payload.get("world_characters") or []:
            if not isinstance(item, dict):
                characters.append(item)
                continue
            next_item = dict(item)
            if (next_item.get("name") or "").strip() == character_name:
                next_item["avatar"] = url
            characters.append(next_item)
        payload["world_characters"] = characters
    else:
        return
    draft.payload = _normalize_world_payload(payload)
    flag_modified(draft, "payload")


def _persist_script_draft_image_url(draft: ScriptDraft, *, url: str) -> None:
    payload = dict(draft.payload or {})
    payload["cover_image"] = url
    draft.payload = _normalize_script_payload(payload)
    flag_modified(draft, "payload")


@router.post("/uploads")
async def upload_image(
    req: UploadImageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """通用图片上传：收 base64 data URL，落 OSS，返回 url。前端把 url 写回草稿 payload。"""
    _require_can_create(user)
    match = _IMAGE_DATA_URL_RE.match(req.image.strip())
    if not match:
        raise HTTPException(status_code=422, detail="图片格式不正确")
    ext = _IMAGE_MIME_EXT.get(match.group("mime"))
    if not ext:
        raise HTTPException(status_code=422, detail="仅支持 PNG / JPEG / WebP 图片")
    try:
        data = base64.b64decode(match.group("b64"), validate=True)
    except Exception as exc:  # noqa: BLE001 — 任何解码失败都按非法图片处理
        raise HTTPException(status_code=422, detail="图片数据无法解析") from exc
    if not data:
        raise HTTPException(status_code=422, detail="图片为空")
    max_bytes = _UPLOAD_MAX_BYTES.get(req.kind, _UPLOAD_MAX_BYTES["cover"])
    if len(data) > max_bytes:
        raise HTTPException(status_code=422, detail=f"图片不能超过 {max_bytes // (1024 * 1024)}MB")

    storage = get_image_storage()
    key = make_image_key(f"uploads/{req.kind}", str(user.id), ext)
    url = await storage.save(data, key)
    return {"code": 0, "data": {"url": url}, "message": "ok"}


@router.post("/world-drafts/{draft_id}/image-prompt")
async def get_world_draft_image_prompt(
    draft_id: str,
    req: WorldImagePromptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """返回单张图片重抽将使用的基础 prompt，供前端回显后让用户编辑。"""
    draft = await db.get(WorldDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="世界草稿不存在")
    _assert_owner(draft, user, "world draft")
    llm_router = await resolve_slot_router(db, "admin_generation") or _get_llm_router()
    try:
        prompt = await build_world_draft_image_prompt(
            db,
            draft,
            target=req.target,
            llm_router=llm_router,
        )
    except ImageRegenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"code": 0, "data": {"prompt": prompt}, "message": "ok"}


@router.post("/script-drafts/{draft_id}/image-prompt")
async def get_script_draft_image_prompt(
    draft_id: str,
    req: ScriptImagePromptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """返回剧本封面重抽将使用的基础 prompt，供前端回显后让用户编辑。"""
    draft = await db.get(ScriptDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="剧本草稿不存在")
    _assert_owner(draft, user, "script draft")
    llm_router = await resolve_slot_router(db, "admin_generation") or _get_llm_router()
    try:
        prompt = await build_script_draft_image_prompt(
            db,
            draft,
            llm_router=llm_router,
        )
    except ImageRegenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"code": 0, "data": {"prompt": prompt}, "message": "ok"}


@router.post("/world-drafts/{draft_id}/regenerate-image")
async def regenerate_world_draft_image_endpoint(
    draft_id: str,
    req: RegenerateWorldImageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """重抽世界草稿的单张图（hero / cover / avatar:<角色名>）。返回新 url，前端写回 payload。"""
    draft = await db.get(WorldDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="世界草稿不存在")
    _assert_owner(draft, user, "world draft")
    llm_router = await resolve_slot_router(db, "admin_generation") or _get_llm_router()
    image_gen = await resolve_slot_image_generator(db, "image_generation")
    try:
        # Cost-attribution seam. NOTE (v1): token_usage requires a session_id or
        # task_id FK to record, and a standalone regen has neither — so this row
        # is dropped and the regen is effectively un-metered. Wiring real metering
        # (mint a task row / reuse the draft's task) is a deliberate follow-up.
        with usage_context(purpose="image_gen", user_id=str(user.id)):
            url = await regenerate_world_draft_image(
                db,
                draft,
                target=req.target,
                hint=req.hint,
                prompt=req.prompt,
                llm_router=llm_router,
                image_gen=image_gen,
            )
    except ImageRegenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _persist_world_draft_image_url(draft, target=req.target, url=url)
    await db.commit()
    return {"code": 0, "data": {"url": url}, "message": "ok"}


@router.post("/script-drafts/{draft_id}/regenerate-image")
async def regenerate_script_draft_image_endpoint(
    draft_id: str,
    req: RegenerateScriptImageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """重抽剧本草稿封面。返回新 url，前端写回 payload。"""
    draft = await db.get(ScriptDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="剧本草稿不存在")
    _assert_owner(draft, user, "script draft")
    llm_router = await resolve_slot_router(db, "admin_generation") or _get_llm_router()
    image_gen = await resolve_slot_image_generator(db, "image_generation")
    try:
        with usage_context(purpose="image_gen", user_id=str(user.id)):
            url = await regenerate_script_draft_image(
                db,
                draft,
                hint=req.hint,
                prompt=req.prompt,
                llm_router=llm_router,
                image_gen=image_gen,
            )
    except ImageRegenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _persist_script_draft_image_url(draft, url=url)
    await db.commit()
    return {"code": 0, "data": {"url": url}, "message": "ok"}


# ---------------------------------------------------------------------------
# World generation tasks
# ---------------------------------------------------------------------------


@router.post("/world-generation-tasks", status_code=201)
async def create_world_generation_task(
    req: CreateWorldGenerationTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_can_create(user)

    if len(req.description) > settings.research_pack_max_admin_description_chars:
        raise HTTPException(
            status_code=422,
            detail=f"description too long (max {settings.research_pack_max_admin_description_chars} chars, got {len(req.description)})",
        )

    try:
        daily_limit = None if user.is_admin else settings.workshop_world_generations_per_day
        await consume_world_generation_quota(db, str(user.id), daily_limit)
    except QuotaExceeded as e:
        raise HTTPException(
            status_code=429,
            detail={"code": 42901, "message": f"Daily world generation quota exceeded ({e.used}/{e.limit})"},
        ) from e

    service = _get_generation_task_service()
    try:
        async with _get_task_limit_lock(user):
            draft_id, task_id = await service.start_world_generation(
                description=req.description,
                genre=req.genre,
                era=req.era,
                user_id=str(user.id),
                phase=PHASE_A,
            )
    except GenerationTaskLimitExceeded as exc:
        raise _generation_task_limit_error(exc) from exc

    await db.commit()
    service.launch_world_generation(task_id)
    return {
        "code": 0,
        "data": {
            "draft_id": draft_id,
            "task_id": task_id,
            "draft_url": f"/workshop/worlds/drafts/{draft_id}",
        },
    }


@router.post("/world-drafts/{draft_id}/continue-generation")
async def continue_world_draft_generation(
    draft_id: str,
    body: ContinueWorldGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """After phase_a Stage 0 task succeeds, pick a fidelity_mode and launch phase_b."""
    _require_can_create(user)

    draft = await db.get(WorldDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    _assert_owner(draft, user, "world draft")

    last_task, _ = await _load_latest_generation_task(
        db, draft_type="world_draft", draft_id=str(draft.id)
    )

    # Idempotency guard — refuse if a phase_b task is already in flight
    if (
        last_task is not None
        and last_task.request_payload is not None
        and last_task.request_payload.get("phase") == PHASE_B
        and last_task.status in {"pending", "running"}
    ):
        raise HTTPException(
            status_code=409,
            detail="A continue-generation task is already running for this draft",
        )

    ip_rec = None
    original_request: dict = {}
    if last_task is not None:
        ip_rec = (last_task.intermediate_state or {}).get("ip_recognition")
        original_request = dict(last_task.request_payload or {})

    payload = dict(draft.payload or {})
    payload["fidelity_mode"] = body.fidelity_mode
    draft.payload = payload
    await db.commit()

    service = _get_generation_task_service()
    try:
        async with _get_task_limit_lock(user):
            new_task_id = await service.start_world_phase_b_task(
                draft_id=str(draft.id),
                description=str(original_request.get("description", "")),
                genre=str(original_request.get("genre", "")),
                era=str(original_request.get("era", "")),
                user_id=str(user.id),
                ip_recognition=ip_rec if isinstance(ip_rec, dict) else None,
                fidelity_mode=body.fidelity_mode,
            )
    except GenerationTaskLimitExceeded as exc:
        raise _generation_task_limit_error(exc) from exc

    await db.commit()
    service.launch_world_generation(new_task_id)
    return {
        "code": 0,
        "data": {"task_id": new_task_id, "draft_id": str(draft.id)},
        "message": "ok",
    }


# ---------------------------------------------------------------------------
# Script generation tasks
# ---------------------------------------------------------------------------


@router.post("/script-premise-suggestions")
async def suggest_script_premises(
    req: ScriptPremiseSuggestionsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """grok 联网选题：给这个世界推荐「下一个剧本」候选（结合 canon + 已有剧本去重）。

    供工坊 picker 用：用户选一个 / 改一个 → 当 outline 发去 /script-generation-tasks。
    """
    _require_can_create(user)

    from services.script_premise_recommender import recommend_script_premises

    service = _get_generation_task_service()
    try:
        world_data = await service.build_script_world_data(db, req.world_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail="world not found") from exc

    agent = await _get_world_creator_agent(db)
    count = max(1, min(req.count, 6))
    premises = await recommend_script_premises(
        world_data=world_data,
        broker=getattr(agent, "research_broker", None),
        llm_router=getattr(agent, "llm", None),
        count=count,
    )
    return {
        "code": 0,
        "data": {
            "world_id": req.world_id,
            "premises": [
                {**p.model_dump(), "outline": p.to_outline()} for p in premises
            ],
        },
        "message": "ok",
    }


@router.post("/script-generation-tasks", status_code=201)
async def create_script_generation_task(
    req: CreateScriptGenerationTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_can_create(user)

    if len(req.outline) > settings.research_pack_max_admin_description_chars:
        raise HTTPException(
            status_code=422,
            detail=f"outline too long (max {settings.research_pack_max_admin_description_chars} chars, got {len(req.outline)})",
        )

    try:
        daily_limit = None if user.is_admin else settings.workshop_script_generations_per_day
        await consume_script_generation_quota(db, str(user.id), daily_limit)
    except QuotaExceeded as e:
        raise HTTPException(
            status_code=429,
            detail={"code": 42902, "message": f"Daily script generation quota exceeded ({e.used}/{e.limit})"},
        ) from e

    service = _get_generation_task_service()
    try:
        async with _get_task_limit_lock(user):
            draft_id, task_id = await service.start_script_generation(
                world_id=req.world_id,
                outline=req.outline,
                user_id=str(user.id),
            )
    except GenerationTaskLimitExceeded as exc:
        raise _generation_task_limit_error(exc) from exc

    await db.commit()
    service.launch_script_generation(task_id)
    return {
        "code": 0,
        "data": {
            "draft_id": draft_id,
            "task_id": task_id,
            "draft_url": f"/workshop/scripts/drafts/{draft_id}",
        },
    }


# ---------------------------------------------------------------------------
# Generation task stream + list/detail
# ---------------------------------------------------------------------------


@router.get("/generation-tasks/{task_id}/stream")
async def stream_generation_task(
    task_id: str,
    after_seq: int = Query(default=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Ownership check before streaming
    task = (await db.execute(select(GenerationTask).where(GenerationTask.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Generation task not found")
    _assert_owner(task, user, "generation task")

    service = _get_generation_task_service()

    async def event_generator():
        async for item in service.stream_task_events(task_id, after_seq=after_seq):
            yield _to_sse_event(item["event"], item["payload"], seq=item.get("seq"))

    return EventSourceResponse(event_generator(), ping=15)


@router.get("/generation-tasks")
async def list_generation_tasks(
    draft_type: str | None = Query(default=None),
    draft_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(GenerationTask).order_by(GenerationTask.created_at.desc())
    if draft_type:
        q = q.where(GenerationTask.draft_type == draft_type)
    if draft_id:
        q = q.where(GenerationTask.draft_id == draft_id)
    # Ownership filter
    if not user.is_admin:
        q = q.where(GenerationTask.created_by_user_id == str(user.id))
    tasks = (await db.execute(q)).scalars().all()
    return {"code": 0, "data": [_serialize_generation_task(t) for t in tasks], "message": "ok"}


@router.get("/generation-tasks/{task_id}")
async def get_generation_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = (await db.execute(select(GenerationTask).where(GenerationTask.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Generation task not found")
    _assert_owner(task, user, "generation task")

    events = (
        await db.execute(
            select(GenerationTaskEvent)
            .where(GenerationTaskEvent.task_id == task.id)
            .order_by(GenerationTaskEvent.seq.asc())
        )
    ).scalars().all()
    return {"code": 0, "data": _serialize_generation_task(task, list(events)), "message": "ok"}


# ---------------------------------------------------------------------------
# Worlds / scripts list (published + my drafts)
# ---------------------------------------------------------------------------


@router.get("/worlds")
async def list_workshop_worlds(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Published worlds (everyone sees) + the caller's own private library
    (admin sees all non-withdrawn). Owner-only worlds are strictly scoped to the
    caller so private content never leaks to other creators."""
    world_q = select(World).order_by(World.created_at.desc())
    if user.is_admin:
        # Admin browses everyone's non-withdrawn content, but must still see
        # their *own* withdrawn worlds (so a withdrawn world stays findable to
        # its owner-admin, shown with the 已下架 badge — mirrors the owner branch).
        world_q = world_q.where(
            or_(
                World.status != "withdrawn",
                World.created_by_user_id == str(user.id),
            )
        )
    else:
        world_q = world_q.where(
            or_(
                World.status == "published",
                World.created_by_user_id == str(user.id),
            )
        )
    worlds = (await db.execute(world_q)).scalars().all()

    # Drafts attached to an existing world — used to mark `has_draft` on published items
    linked_q = select(WorldDraft).where(WorldDraft.world_id.is_not(None)).order_by(WorldDraft.updated_at.desc())
    new_q = select(WorldDraft).where(WorldDraft.world_id.is_(None)).order_by(WorldDraft.updated_at.desc())
    if not user.is_admin:
        linked_q = linked_q.where(WorldDraft.created_by_user_id == str(user.id))
        new_q = new_q.where(WorldDraft.created_by_user_id == str(user.id))

    linked_drafts = (await db.execute(linked_q)).scalars().all()
    new_drafts = (await db.execute(new_q)).scalars().all()

    draft_by_world_id = {d.world_id: d for d in linked_drafts if d.world_id}
    new_draft_ids = [d.id for d in new_drafts]

    world_tasks = []
    if new_draft_ids:
        world_tasks = (
            await db.execute(
                select(GenerationTask)
                .where(
                    GenerationTask.draft_type == "world_draft",
                    GenerationTask.draft_id.in_(new_draft_ids),
                )
                .order_by(GenerationTask.created_at.desc())
            )
        ).scalars().all()
    latest_task_by_draft: dict[str, GenerationTask] = {}
    for task in world_tasks:
        latest_task_by_draft.setdefault(str(task.draft_id), task)

    script_count_rows = (
        await db.execute(select(Script.world_id, func.count(Script.id)).group_by(Script.world_id))
    ).all()
    script_count_by_world: dict = {row[0]: int(row[1]) for row in script_count_rows}

    published_items = []
    for world in worlds:
        images = resolve_world_image_fields_from_model(world)
        draft = draft_by_world_id.get(world.id)
        if draft:
            draft_images = resolve_world_image_fields_from_mapping(draft.payload)
            images = {
                "cover_image": _prefer_draft_image(draft_images["cover_image"], images["cover_image"]),
                "hero_image": _prefer_draft_image(draft_images["hero_image"], images["hero_image"]),
            }
        images = _normalize_workshop_image_fields(images)
        published_items.append({
            "id": str(world.id),
            "name": world.name,
            "description": world.description,
            "genre": world.genre,
            "era": world.era,
            "cover_image": images["cover_image"],
            "hero_image": images["hero_image"],
            "status": world.status,
            # owner-only actions (publish / withdraw / edit) are gated on this
            "is_owner": str(world.created_by_user_id) == str(user.id),
            "has_draft": draft is not None,
            "draft_id": str(draft.id) if draft else None,
            "review_status": (
                draft.review_status if draft else "editing"
            ),
            "review_note": (
                draft.review_note if draft else None
            ),
            "script_count": script_count_by_world.get(world.id, 0),
        })

    draft_items = []
    for draft in new_drafts:
        images = resolve_world_image_fields_from_mapping(draft.payload)
        images = _normalize_workshop_image_fields(images)
        latest_task = latest_task_by_draft.get(str(draft.id))
        draft_items.append({
            "id": str(draft.id),
            "name": (draft.payload or {}).get("name", "未命名世界草稿"),
            "description": (draft.payload or {}).get("description", ""),
            "cover_image": images["cover_image"],
            "hero_image": images["hero_image"],
            "world_id": None,
            "updated_at": serialize_utc_datetime(draft.updated_at),
            "generation_status": latest_task.status if latest_task else None,
            "generation_task_id": str(latest_task.id) if latest_task else None,
        })

    return {"code": 0, "data": {"published": published_items, "drafts": draft_items}}


@router.get("/scripts")
async def list_workshop_scripts(
    world_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Published scripts for a world (everyone sees) + the caller's own private
    scripts in that world (admin sees all) + the caller's own drafts."""
    world = await db.get(World, world_id)
    if not world:
        raise HTTPException(status_code=404, detail="世界不存在")

    script_q = (
        select(Script)
        .where(Script.world_id == world.id)
        .order_by(Script.created_at.desc())
    )
    if not user.is_admin:
        script_q = script_q.where(
            or_(Script.is_published.is_(True), Script.created_by_user_id == str(user.id))
        )
    scripts = (await db.execute(script_q)).scalars().all()

    linked_q = (
        select(ScriptDraft)
        .where(ScriptDraft.world_id == world.id)
        .where(ScriptDraft.script_id.is_not(None))
        .order_by(ScriptDraft.updated_at.desc())
    )
    new_q = (
        select(ScriptDraft)
        .where(ScriptDraft.world_id == world.id)
        .where(ScriptDraft.script_id.is_(None))
        .order_by(ScriptDraft.updated_at.desc())
    )
    if not user.is_admin:
        linked_q = linked_q.where(ScriptDraft.created_by_user_id == str(user.id))
        new_q = new_q.where(ScriptDraft.created_by_user_id == str(user.id))

    linked_drafts = (await db.execute(linked_q)).scalars().all()
    new_drafts = (await db.execute(new_q)).scalars().all()

    draft_by_script_id = {d.script_id: d for d in linked_drafts if d.script_id}
    new_draft_ids = [d.id for d in new_drafts]

    script_tasks = []
    if new_draft_ids:
        script_tasks = (
            await db.execute(
                select(GenerationTask)
                .where(
                    GenerationTask.draft_type == "script_draft",
                    GenerationTask.draft_id.in_(new_draft_ids),
                )
                .order_by(GenerationTask.created_at.desc())
            )
        ).scalars().all()
    latest_task_by_draft: dict[str, GenerationTask] = {}
    for task in script_tasks:
        latest_task_by_draft.setdefault(str(task.draft_id), task)

    return {
        "code": 0,
        "data": {
            "world": {"id": str(world.id), "name": world.name},
            "published": [
                {
                    "id": str(s.id),
                    "name": s.name,
                    "description": s.description,
                    "cover_image": s.cover_image,
                    "difficulty": s.difficulty,
                    "estimated_time": s.estimated_time,
                    "status": s.status,
                    "is_published": s.is_published,
                    "is_owner": str(s.created_by_user_id) == str(user.id),
                    "has_draft": s.id in draft_by_script_id,
                    "draft_id": str(draft_by_script_id[s.id].id) if s.id in draft_by_script_id else None,
                    "review_status": (
                        draft_by_script_id[s.id].review_status if s.id in draft_by_script_id else "editing"
                    ),
                    "review_note": (
                        draft_by_script_id[s.id].review_note if s.id in draft_by_script_id else None
                    ),
                }
                for s in scripts
            ],
            "drafts": [
                {
                    "id": str(d.id),
                    "world_id": str(d.world_id),
                    "name": (d.payload or {}).get("name", "未命名剧本草稿"),
                    "description": (d.payload or {}).get("description", ""),
                    "cover_image": (d.payload or {}).get("cover_image"),
                    "updated_at": serialize_utc_datetime(d.updated_at),
                    "generation_status": latest_task_by_draft.get(str(d.id)).status if latest_task_by_draft.get(str(d.id)) else None,
                    "generation_task_id": str(latest_task_by_draft.get(str(d.id)).id) if latest_task_by_draft.get(str(d.id)) else None,
                }
                for d in new_drafts
            ],
        },
    }


# ---------------------------------------------------------------------------
# World drafts CRUD
# ---------------------------------------------------------------------------


@router.get("/world-drafts")
async def list_world_drafts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(WorldDraft).order_by(WorldDraft.updated_at.desc())
    q = _ownership_filter(q, WorldDraft, user)
    drafts = (await db.execute(q)).scalars().all()
    return {"code": 0, "data": [_world_draft_detail(d) for d in drafts], "message": "ok"}


@router.post("/world-drafts", status_code=201)
async def create_world_draft(
    req: CreateWorldDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_can_create(user)

    if req.world_id:
        existing = (
            await db.execute(select(WorldDraft).where(WorldDraft.world_id == req.world_id))
        ).scalar_one_or_none()
        if existing:
            _assert_owner(existing, user, "world draft")
            return {"code": 0, "data": _world_draft_detail(existing)}

        world = await db.get(World, req.world_id)
        if not world:
            raise HTTPException(status_code=404, detail="世界不存在")

        world_chars = (
            await db.execute(select(WorldCharacter).where(WorldCharacter.world_id == world.id))
        ).scalars().all()
        draft = WorldDraft(
            world_id=world.id,
            payload=_world_payload_from_models(world, world_chars),
            created_by_user_id=str(user.id),
        )
    elif req.payload:
        draft = WorldDraft(
            payload=_normalize_world_payload(req.payload),
            created_by_user_id=str(user.id),
        )
    else:
        raise HTTPException(status_code=400, detail="必须提供 world_id 或 payload")

    db.add(draft)
    await db.flush()
    await db.commit()
    await db.refresh(draft)
    task, events = await _load_latest_generation_task(db, draft_type="world_draft", draft_id=str(draft.id))
    return {"code": 0, "data": _world_draft_detail(draft, generation_task=task, generation_events=events)}


@router.get("/world-drafts/{draft_id}")
async def get_world_draft(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft = await db.get(WorldDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="世界草稿不存在")
    _assert_owner(draft, user, "world draft")
    task, events = await _load_latest_generation_task(db, draft_type="world_draft", draft_id=str(draft.id))
    return {"code": 0, "data": _world_draft_detail(draft, generation_task=task, generation_events=events)}


@router.put("/world-drafts/{draft_id}")
async def update_world_draft(
    draft_id: str,
    req: UpdateWorldDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft = await db.get(WorldDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="世界草稿不存在")
    _assert_owner(draft, user, "world draft")
    draft.payload = _normalize_world_payload(req.payload)
    await db.commit()
    await db.refresh(draft)
    task, events = await _load_latest_generation_task(db, draft_type="world_draft", draft_id=str(draft.id))
    return {"code": 0, "data": _world_draft_detail(draft, generation_task=task, generation_events=events)}


@router.delete("/world-drafts/{draft_id}")
async def delete_world_draft(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from models.ip_knowledge_pack import IPKnowledgePack as _IPK
    draft = await db.get(WorldDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="世界草稿不存在")
    _assert_owner(draft, user, "world draft")
    # draft 关联的 IP Pack 已无意义，直接删掉避免 FK 阻塞
    await db.execute(delete(_IPK).where(_IPK.draft_id == draft_id))
    await db.delete(draft)
    await db.commit()
    return {"code": 0, "data": None, "message": "ok"}


@router.post("/world-drafts/{draft_id}/save-private")
async def save_world_draft_private_endpoint(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存为私有作品：把草稿落成 owner-only 可玩的 World（不进全网 feed）。"""
    try:
        world = await publish_service.save_world_as_private(
            db,
            draft_id=draft_id,
            actor_user_id=str(user.id),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 0, "data": {"world_id": str(world.id), "status": world.status}, "message": "ok"}


@router.post("/world-drafts/{draft_id}/publish")
async def publish_world_draft_endpoint(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        world = await publish_service.publish_world_draft(
            db,
            draft_id=draft_id,
            actor_user_id=str(user.id),
            audit_enabled=False,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 0, "data": {"world_id": str(world.id), "status": world.status}, "message": "ok"}


# ---------------------------------------------------------------------------
# Script drafts CRUD
# ---------------------------------------------------------------------------


@router.get("/script-drafts")
async def list_script_drafts(
    world_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(ScriptDraft).order_by(ScriptDraft.updated_at.desc())
    if world_id:
        q = q.where(ScriptDraft.world_id == world_id)
    q = _ownership_filter(q, ScriptDraft, user)
    drafts = (await db.execute(q)).scalars().all()
    return {"code": 0, "data": [_script_draft_detail(d) for d in drafts], "message": "ok"}


@router.post("/script-drafts", status_code=201)
async def create_script_draft(
    req: CreateScriptDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_can_create(user)

    if req.script_id:
        existing = (
            await db.execute(select(ScriptDraft).where(ScriptDraft.script_id == req.script_id))
        ).scalar_one_or_none()
        if existing:
            _assert_owner(existing, user, "script draft")
            wpc = await _load_world_playable_characters(db, str(existing.world_id))
            return {"code": 0, "data": _script_draft_detail(existing, world_playable_characters=wpc)}

        script = await db.get(Script, req.script_id)
        if not script:
            raise HTTPException(status_code=404, detail="剧本不存在")
        draft = ScriptDraft(
            world_id=script.world_id,
            script_id=script.id,
            payload=_script_payload_from_model(script),
            created_by_user_id=str(user.id),
        )
    elif req.world_id and req.payload:
        world = await db.get(World, req.world_id)
        if not world:
            raise HTTPException(status_code=404, detail="世界不存在")
        draft = ScriptDraft(
            world_id=world.id,
            payload=_normalize_script_payload(req.payload),
            created_by_user_id=str(user.id),
        )
    else:
        raise HTTPException(status_code=400, detail="必须提供 script_id 或 world_id + payload")

    db.add(draft)
    await db.flush()
    await db.commit()
    await db.refresh(draft)
    task, events = await _load_latest_generation_task(db, draft_type="script_draft", draft_id=str(draft.id))
    wpc = await _load_world_playable_characters(db, str(draft.world_id))
    return {
        "code": 0,
        "data": _script_draft_detail(
            draft, generation_task=task, generation_events=events, world_playable_characters=wpc
        ),
    }


@router.get("/script-drafts/{draft_id}")
async def get_script_draft(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft = await db.get(ScriptDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="剧本草稿不存在")
    _assert_owner(draft, user, "script draft")
    task, events = await _load_latest_generation_task(db, draft_type="script_draft", draft_id=str(draft.id))
    wpc = await _load_world_playable_characters(db, str(draft.world_id))
    return {
        "code": 0,
        "data": _script_draft_detail(
            draft, generation_task=task, generation_events=events, world_playable_characters=wpc
        ),
    }


@router.put("/script-drafts/{draft_id}")
async def update_script_draft(
    draft_id: str,
    req: UpdateScriptDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft = await db.get(ScriptDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="剧本草稿不存在")
    _assert_owner(draft, user, "script draft")
    draft.payload = _normalize_script_payload(req.payload)
    await db.commit()
    await db.refresh(draft)
    task, events = await _load_latest_generation_task(db, draft_type="script_draft", draft_id=str(draft.id))
    wpc = await _load_world_playable_characters(db, str(draft.world_id))
    return {
        "code": 0,
        "data": _script_draft_detail(
            draft, generation_task=task, generation_events=events, world_playable_characters=wpc
        ),
    }


@router.delete("/script-drafts/{draft_id}")
async def delete_script_draft(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft = await db.get(ScriptDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="剧本草稿不存在")
    _assert_owner(draft, user, "script draft")
    await db.delete(draft)
    await db.commit()
    return {"code": 0, "data": None, "message": "ok"}


@router.post("/script-drafts/{draft_id}/save-private")
async def save_script_draft_private_endpoint(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存为私有作品：把剧本草稿落成 owner-only 可玩的 Script。"""
    try:
        script = await publish_service.save_script_as_private(
            db,
            draft_id=draft_id,
            actor_user_id=str(user.id),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 0, "data": {"script_id": str(script.id), "status": script.status}, "message": "ok"}


@router.post("/script-drafts/{draft_id}/publish")
async def publish_script_draft_endpoint(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        script = await publish_service.publish_script_draft(
            db,
            draft_id=draft_id,
            actor_user_id=str(user.id),
            audit_enabled=False,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 0, "data": {"script_id": str(script.id), "status": script.status}, "message": "ok"}


# ---------------------------------------------------------------------------
# Submit for review / withdraw submission (owner)
# ---------------------------------------------------------------------------


@router.post("/world-drafts/{draft_id}/submit")
async def submit_world_draft_endpoint(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提交发布：把私有世界提交 admin 审核（草稿 review_status=submitted）。"""
    try:
        draft = await publish_service.submit_world_for_review(
            db, draft_id=draft_id, actor_user_id=str(user.id)
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 0, "data": {"review_status": draft.review_status}, "message": "ok"}


@router.post("/world-drafts/{draft_id}/withdraw-submission")
async def withdraw_world_submission_endpoint(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """撤回提交：审核中 → 回到私有可编辑。"""
    try:
        draft = await publish_service.withdraw_world_submission(
            db, draft_id=draft_id, actor_user_id=str(user.id)
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 0, "data": {"review_status": draft.review_status}, "message": "ok"}


@router.post("/script-drafts/{draft_id}/submit")
async def submit_script_draft_endpoint(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提交发布：把私有剧本提交审核（要求其世界已 published）。"""
    try:
        draft = await publish_service.submit_script_for_review(
            db, draft_id=draft_id, actor_user_id=str(user.id)
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 0, "data": {"review_status": draft.review_status}, "message": "ok"}


@router.post("/script-drafts/{draft_id}/withdraw-submission")
async def withdraw_script_submission_endpoint(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        draft = await publish_service.withdraw_script_submission(
            db, draft_id=draft_id, actor_user_id=str(user.id)
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 0, "data": {"review_status": draft.review_status}, "message": "ok"}


# ---------------------------------------------------------------------------
# Withdraw
# ---------------------------------------------------------------------------


@router.post("/worlds/{world_id}/withdraw")
async def withdraw_world_endpoint(
    world_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        world = await publish_service.withdraw_world(
            db,
            world_id=world_id,
            actor_user_id=str(user.id),
            by_admin=user.is_admin,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 0, "data": {"world_id": str(world.id), "status": world.status}, "message": "ok"}


@router.post("/scripts/{script_id}/withdraw")
async def withdraw_script_endpoint(
    script_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        script = await publish_service.withdraw_script(
            db,
            script_id=script_id,
            actor_user_id=str(user.id),
            by_admin=user.is_admin,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 0, "data": {"script_id": str(script.id), "status": script.status}, "message": "ok"}


# ---------------------------------------------------------------------------
# Hard delete (worlds / scripts)
# ---------------------------------------------------------------------------


from services.delete_service import (  # noqa: E402  (kept near use site)
    DeleteConflictError,
    delete_script as _delete_script_service,
    delete_world as _delete_world_service,
)


@router.delete("/worlds/{world_id}")
async def delete_world_endpoint(
    world_id: str,
    force: bool = Query(default=False, description="admin only — bypass active-session / child-script guards"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """硬删世界，owner 或 admin 可调。

    冲突时返回 409：(a) 有玩家正在该世界游玩 (b) 该世界下还有剧本未删。
    admin 传 force=true 可绕过；非 admin 即便传 force 也无效。
    """
    try:
        result = await _delete_world_service(
            db,
            world_id=world_id,
            actor_user_id=str(user.id),
            by_admin=user.is_admin,
            force=force,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except DeleteConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"code": 0, "data": result, "message": "ok"}


@router.delete("/scripts/{script_id}")
async def delete_script_endpoint(
    script_id: str,
    force: bool = Query(default=False, description="admin only — bypass active-session guard"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """硬删剧本，owner 或 admin 可调。

    冲突时返回 409：有玩家正在该剧本游玩。admin 传 force=true 可绕过。
    """
    try:
        result = await _delete_script_service(
            db,
            script_id=script_id,
            actor_user_id=str(user.id),
            by_admin=user.is_admin,
            force=force,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except DeleteConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"code": 0, "data": result, "message": "ok"}
