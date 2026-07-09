"""Single-image regeneration for workshop drafts.

Regenerate ONE image (world hero / world cover / a character avatar / script
cover) from the *current* draft fields, optionally steered by a free-text hint.
Reuses the ``cover_brief`` pipeline (so a regen reflects the creator's latest
edits + the mood-derivation that keeps images off the商业海报均值) and the
agent's image-gen-with-fallback helper.

Returns the new OSS URL; the caller writes it back into the draft payload. The
service never mutates the draft itself.
"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llm.base import ImageGenerator
from llm.router import LLMRouter
from models.draft import ScriptDraft, WorldDraft
from models.ip_knowledge_pack import IPKnowledgePack
from models.world import World
from services.cover_brief import (
    CharacterCoverBrief,
    CoverBrief,
    build_character_portrait_prompt,
    build_script_cover_prompt,
    build_world_cover_prompt,
    build_world_hero_prompt,
)
from services.cover_brief_helper import derive_world_cover_brief
from services.image_storage import (
    IMAGE_PLACEHOLDER_URL,
    get_image_storage,
    make_image_key,
)
from services.ip_recognizer import IPRecognition
from services.world_creator_agent_v2 import _generate_image_with_fallback

logger = structlog.get_logger()

# World-draft image targets.
TARGET_HERO = "hero"
TARGET_COVER = "cover"
_AVATAR_PREFIX = "avatar:"


class ImageRegenerationError(Exception):
    """Raised when a single-image regeneration cannot produce a usable image.

    The caller maps this to a 4xx/5xx and keeps the old image in place.
    """


def _append_hint(prompt: str, hint: str) -> str:
    """Append the creator's free-text steering to a built prompt."""
    hint = (hint or "").strip()
    if not hint:
        return prompt
    return f"{prompt}\n补充要求（请优先满足）：{hint}"


def _world_data_from_payload(payload: dict) -> dict:
    research_summary = (
        ((payload.get("research_pack") or {}).get("summary") or "")[:800]
    )
    return {
        "name": (payload.get("name") or "").strip(),
        "genre": (payload.get("genre") or "").strip(),
        "era": (payload.get("era") or "").strip(),
        "description": (payload.get("description") or "").strip(),
        "research_summary": research_summary,
        "visual_style": payload.get("visual_style") if isinstance(payload.get("visual_style"), dict) else None,
        "lore_pack": payload.get("lore_pack") if isinstance(payload.get("lore_pack"), dict) else None,
    }


async def _recognition_for_draft(
    db: AsyncSession, draft_id: str
) -> IPRecognition | None:
    """Rebuild a high-confidence ``IPRecognition`` from the draft's IP pack so a
    regen keeps the world's IP visual anchor.

    ``ip_pack`` (which drives per-character ``reference_anchor``) is intentionally
    NOT reconstructed in v1 — IP-world avatar regens fall back to the LLM-derived
    4-dim descriptor, which is still per-character and on-tone.
    """
    pack = (
        (
            await db.execute(
                select(IPKnowledgePack).where(IPKnowledgePack.draft_id == draft_id)
            )
        )
        .scalars()
        .first()
    )
    if pack is None:
        return None
    ip_name = (pack.ip_name or "").strip()
    if not ip_name:
        return None
    return IPRecognition(kind="known_ip", confidence=1.0, ip_name=ip_name)


def _clean_prompt_override(prompt: str | None) -> str:
    return (prompt or "").strip()


def _tiers(base: str, fallback: str | None, hint: str, prompt: str | None = None) -> list[str]:
    """Build prompt tiers (with optional IP-fallback escalation), hint appended."""
    prompt_override = _clean_prompt_override(prompt)
    if prompt_override:
        return [prompt_override]
    tiers = [_append_hint(base, hint)]
    if fallback is not None:
        tiers.append(_append_hint(fallback, hint))
    return tiers


async def build_world_draft_image_prompt(
    db: AsyncSession,
    draft: WorldDraft,
    *,
    target: str,
    llm_router: LLMRouter,
) -> str:
    """Return the base image prompt for one world-draft image target."""
    payload = draft.payload or {}
    world_data = _world_data_from_payload(payload)
    recognition = await _recognition_for_draft(db, str(draft.id))

    if target in (TARGET_HERO, TARGET_COVER):
        world_brief, _ = await derive_world_cover_brief(
            world_data=world_data,
            characters=[],
            recognition=recognition,
            ip_pack=None,
            llm=llm_router,
        )
        if target == TARGET_HERO:
            return build_world_hero_prompt(world_brief)
        return build_world_cover_prompt(world_brief)

    if target.startswith(_AVATAR_PREFIX):
        char_name = target[len(_AVATAR_PREFIX) :].strip()
        if not char_name:
            raise ImageRegenerationError("缺少角色名")
        chars = payload.get("world_characters") or []
        char = next(
            (c for c in chars if (c.get("name") or "").strip() == char_name), None
        )
        if char is None:
            raise ImageRegenerationError(f"角色不存在：{char_name}")
        char_input = {
            "name": char_name,
            "personality": char.get("personality", ""),
            "gender": char.get("gender", ""),
            "role_tag": char.get("role_tag", ""),
            "is_image_target": True,
        }
        world_brief, char_briefs = await derive_world_cover_brief(
            world_data=world_data,
            characters=[char_input],
            recognition=recognition,
            ip_pack=None,
            llm=llm_router,
        )
        char_brief = char_briefs.get(char_name) or CharacterCoverBrief(name=char_name)
        return build_character_portrait_prompt(world_brief, char_brief)

    raise ImageRegenerationError(f"不支持的图片目标：{target}")


async def build_script_draft_image_prompt(
    db: AsyncSession,
    draft: ScriptDraft,
    *,
    llm_router: LLMRouter,
) -> str:
    """Return the base image prompt for a script-draft cover."""
    payload = draft.payload or {}
    world = await db.get(World, draft.world_id)
    if world is None:
        raise ImageRegenerationError("剧本所属世界不存在")

    world_data = {
        "name": (world.name or "").strip(),
        "genre": (getattr(world, "genre", "") or "").strip(),
        "era": (getattr(world, "era", "") or "").strip(),
        "description": (world.description or "").strip(),
        "lore_pack": world.lore_pack if isinstance(world.lore_pack, dict) else None,
        "visual_style": (world.lore_pack or {}).get("visual_style") if isinstance(world.lore_pack, dict) else None,
    }
    pack = (
        (
            await db.execute(
                select(IPKnowledgePack).where(IPKnowledgePack.world_id == str(world.id))
            )
        )
        .scalars()
        .first()
    )
    recognition: IPRecognition | None = None
    if pack is not None and (pack.ip_name or "").strip():
        recognition = IPRecognition(
            kind="known_ip", confidence=1.0, ip_name=pack.ip_name.strip()
        )

    world_brief, _ = await derive_world_cover_brief(
        world_data=world_data,
        characters=[],
        recognition=recognition,
        ip_pack=None,
        llm=llm_router,
    )
    return build_script_cover_prompt(
        world_brief,
        script_title=(payload.get("name") or "").strip(),
        script_title_english="",
        script_essence=(payload.get("description") or "").strip(),
    )


async def _generate_one(
    *,
    image_gen: ImageGenerator,
    prompt_tiers: list[str],
    aspect_ratio: str,
    category: str,
    name: str,
    log_key: str,
) -> str:
    storage = get_image_storage()
    storage_key = make_image_key(category, name or "image")
    url, _result = await _generate_image_with_fallback(
        image_gen,
        prompt_tiers,
        aspect_ratio=aspect_ratio,
        storage=storage,
        storage_key=storage_key,
        log_key=log_key,
    )
    if not url or url == IMAGE_PLACEHOLDER_URL:
        raise ImageRegenerationError("图片生成失败，请稍后重试")
    return url


async def regenerate_world_draft_image(
    db: AsyncSession,
    draft: WorldDraft,
    *,
    target: str,
    hint: str,
    prompt: str | None = None,
    llm_router: LLMRouter,
    image_gen: ImageGenerator | None,
) -> str:
    """Regenerate one world-draft image. ``target`` ∈ {"hero", "cover",
    "avatar:<角色名>"}. Returns the new image URL."""
    if image_gen is None:
        raise ImageRegenerationError("未配置图像生成服务")

    payload = draft.payload or {}
    world_data = _world_data_from_payload(payload)
    recognition = await _recognition_for_draft(db, str(draft.id))

    if target in (TARGET_HERO, TARGET_COVER):
        world_brief, _ = await derive_world_cover_brief(
            world_data=world_data,
            characters=[],
            recognition=recognition,
            ip_pack=None,
            llm=llm_router,
        )
        is_ip = bool(world_brief.ip_name and world_brief.ip_name.strip())
        if target == TARGET_HERO:
            base = build_world_hero_prompt(world_brief)
            fallback = build_world_hero_prompt(world_brief, ip_fallback=True) if is_ip else None
            aspect, category = "21:9", "worlds/hero"
        else:
            base = build_world_cover_prompt(world_brief)
            fallback = build_world_cover_prompt(world_brief, ip_fallback=True) if is_ip else None
            aspect, category = "3:2", "worlds/cover"
        return await _generate_one(
            image_gen=image_gen,
            prompt_tiers=_tiers(base, fallback, hint, prompt),
            aspect_ratio=aspect,
            category=category,
            name=world_data["name"],
            log_key=f"world:{target}",
        )

    if target.startswith(_AVATAR_PREFIX):
        char_name = target[len(_AVATAR_PREFIX) :].strip()
        if not char_name:
            raise ImageRegenerationError("缺少角色名")
        chars = payload.get("world_characters") or []
        char = next(
            (c for c in chars if (c.get("name") or "").strip() == char_name), None
        )
        if char is None:
            raise ImageRegenerationError(f"角色不存在：{char_name}")
        char_input = {
            "name": char_name,
            "personality": char.get("personality", ""),
            "gender": char.get("gender", ""),
            "role_tag": char.get("role_tag", ""),
            "is_image_target": True,
        }
        world_brief, char_briefs = await derive_world_cover_brief(
            world_data=world_data,
            characters=[char_input],
            recognition=recognition,
            ip_pack=None,
            llm=llm_router,
        )
        char_brief = char_briefs.get(char_name) or CharacterCoverBrief(name=char_name)
        base_prompt = build_character_portrait_prompt(world_brief, char_brief)
        return await _generate_one(
            image_gen=image_gen,
            prompt_tiers=_tiers(base_prompt, None, hint, prompt),
            aspect_ratio="2:3",
            category="characters",
            name=char_name,
            log_key=f"avatar:{char_name}",
        )

    raise ImageRegenerationError(f"不支持的图片目标：{target}")


async def regenerate_script_draft_image(
    db: AsyncSession,
    draft: ScriptDraft,
    *,
    hint: str,
    prompt: str | None = None,
    llm_router: LLMRouter,
    image_gen: ImageGenerator | None,
) -> str:
    """Regenerate a script draft's 3:2 cover. Returns the new image URL."""
    if image_gen is None:
        raise ImageRegenerationError("未配置图像生成服务")

    payload = draft.payload or {}
    world = await db.get(World, draft.world_id)
    if world is None:
        raise ImageRegenerationError("剧本所属世界不存在")

    world_data = {
        "name": (world.name or "").strip(),
        "genre": (getattr(world, "genre", "") or "").strip(),
        "era": (getattr(world, "era", "") or "").strip(),
        "description": (world.description or "").strip(),
        "lore_pack": world.lore_pack if isinstance(world.lore_pack, dict) else None,
        "visual_style": (world.lore_pack or {}).get("visual_style") if isinstance(world.lore_pack, dict) else None,
    }
    # The parent world is published, so its IP pack (if any) lives under world_id.
    pack = (
        (
            await db.execute(
                select(IPKnowledgePack).where(IPKnowledgePack.world_id == str(world.id))
            )
        )
        .scalars()
        .first()
    )
    recognition: IPRecognition | None = None
    if pack is not None and (pack.ip_name or "").strip():
        recognition = IPRecognition(
            kind="known_ip", confidence=1.0, ip_name=pack.ip_name.strip()
        )

    world_brief, _ = await derive_world_cover_brief(
        world_data=world_data,
        characters=[],
        recognition=recognition,
        ip_pack=None,
        llm=llm_router,
    )
    script_title = (payload.get("name") or "").strip()
    script_essence = (payload.get("description") or "").strip()
    is_ip = bool(world_brief.ip_name and world_brief.ip_name.strip())
    base = build_script_cover_prompt(
        world_brief,
        script_title=script_title,
        script_title_english="",
        script_essence=script_essence,
    )
    fallback = (
        build_script_cover_prompt(
            world_brief,
            script_title=script_title,
            script_title_english="",
            script_essence=script_essence,
            ip_fallback=True,
        )
        if is_ip
        else None
    )
    return await _generate_one(
        image_gen=image_gen,
        prompt_tiers=_tiers(base, fallback, hint, prompt),
        aspect_ratio="3:2",
        category="scripts/cover",
        name=script_title or "script",
        log_key="script:cover",
    )
