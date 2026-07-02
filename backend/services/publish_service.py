"""Publish/withdraw service for user-owned worlds and scripts.

Handles state transitions driven by the ContentStatus state machine.
Pure payload helpers (_normalize_*, _compose_*, _coerce_*) are defined here
and re-exported so admin.py can import from a single place (DRY).
"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from engine.content_status import (
    ContentStatus,
    can_transition,
    next_status_on_publish,
    next_status_on_withdraw,
)

publish_logger = structlog.get_logger("publish_service")
from models.draft import ScriptDraft, WorldDraft
from models.game import GameSession
from models.script import Script
from services import notification_service as ns
from sqlalchemy import delete as sa_delete
from models.world import Ending, World, WorldCharacter
from services.cross_artifact_validator import (
    CrossArtifactError,
    validate_cross_artifact,
)
from services.generation_schema import (
    SchemaValidationError,
    validate_script_payload,
    validate_world_payload,
)
from services.world_image_fields import resolve_world_image_fields_from_mapping

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOCATION_BLOCK_HEADER = "## 地点列表"
IMAGE_PLACEHOLDER_URL = "/static/placeholder-cover.png"

# ---------------------------------------------------------------------------
# Pure payload / coercion helpers  (exported so admin.py can import them)
# ---------------------------------------------------------------------------

_DIFFICULTY_STRING_MAP = {"easy": 2, "medium": 3, "hard": 4}


def _derive_narrative_weight(wc_data: dict) -> int:
    """Map v2 roster planner signals (role_tag / is_image_target) to a 0-100
    importance score. World detail page sorts characters by this so the
    protagonist surfaces first. Admin can override later via the editor.
    """
    role_tag = (wc_data.get("role_tag") or "").strip()
    if "主角" in role_tag or role_tag == "主":
        return 100
    if "宿敌" in role_tag or "反派" in role_tag:
        return 90
    if wc_data.get("is_image_target"):
        return 70
    return 50


def _coerce_difficulty(value, default: int = 3) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if 1 <= value <= 5 else default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _DIFFICULTY_STRING_MAP:
            return _DIFFICULTY_STRING_MAP[normalized]
        if normalized.isdigit():
            n = int(normalized)
            return n if 1 <= n <= 5 else default
    return default


def _is_placeholder_image(value: object) -> bool:
    return isinstance(value, str) and value.strip() == IMAGE_PLACEHOLDER_URL


def _coerce_world_character(
    raw,
    *,
    avatar_override: str | None = None,
    playable_override: bool = False,
) -> dict:
    """LLM emits ``null`` for fields the DB requires NOT NULL.

    ``dict.get(key, default)`` won't substitute the default when the key is
    present with a None value, so we coerce explicitly here.  Nullable columns
    (secret, description, avatar, initial_peer_relations) pass through unchanged.
    """
    if not isinstance(raw, dict):
        return {}
    # v2 roster planner 字段（role_tag / faction / is_image_target）也要 forward
    # 进 draft.payload：前端用 is_image_target 决定是否显示头像格子；admin UI 用
    # role_tag 显示标签；publish 时这些字段可能没有对应 DB 列，但 draft JSON 列
    # 能保留完整状态，再次进 admin 编辑器时还原。
    return {
        "name": raw.get("name") or "",
        "personality": raw.get("personality") or "",
        # voice_style / gender 是生成阶段产出的内容字段（voice_style 决定 NPC 对白
        # 口吻，运行时注入 npc_agent；gender 喂封面/头像 pipeline）。此前漏 forward，
        # 导致 LLM 生成好的 voice_style 在写库时被整体丢弃 → NPC 千人一腔。
        "voice_style": raw.get("voice_style") or "",
        "gender": raw.get("gender") or "",
        "secret": raw.get("secret"),
        "knowledge": raw.get("knowledge") or [],
        "schedule": raw.get("schedule") or {},
        "initial_location": raw.get("initial_location") or "",
        "playable": bool(raw.get("playable")) or playable_override,
        "description": raw.get("description"),
        "abilities": raw.get("abilities") or [],
        "starting_inventory": raw.get("starting_inventory") or [],
        "avatar": avatar_override if avatar_override is not None else raw.get("avatar"),
        "initial_peer_relations": raw.get("initial_peer_relations"),
        # v2 fields — preserve so the draft can re-hydrate the full roster state
        "role_tag": raw.get("role_tag") or "",
        "faction": raw.get("faction") or "",
        "is_image_target": bool(raw.get("is_image_target")),
    }


def _split_world_setting(
    base_setting: str, locations_data: list[dict] | None = None
) -> tuple[str, list[dict]]:
    if locations_data:
        marker = f"\n\n{LOCATION_BLOCK_HEADER}\n"
        if marker in base_setting:
            return base_setting.split(marker, 1)[0].strip(), locations_data
        return base_setting.strip(), locations_data

    marker = f"\n\n{LOCATION_BLOCK_HEADER}\n"
    if marker not in base_setting:
        return base_setting.strip(), []

    raw_setting, block = base_setting.split(marker, 1)
    locations: list[dict] = []
    for line in block.splitlines():
        entry = line.strip()
        if not entry.startswith("- "):
            continue
        text = entry[2:]
        if "：" in text:
            name, description = text.split("：", 1)
        elif ":" in text:
            name, description = text.split(":", 1)
        else:
            name, description = text, ""
        locations.append({"name": name.strip(), "description": description.strip()})
    return raw_setting.strip(), locations


def _compose_world_setting(base_setting: str, locations: list[dict]) -> str:
    clean_setting = base_setting.strip()
    if not locations:
        return clean_setting

    location_block = "\n".join(
        f"- {location.get('name', '').strip()}：{location.get('description', '').strip()}"
        for location in locations
        if location.get("name")
    )
    if not location_block:
        return clean_setting
    return f"{clean_setting}\n\n{LOCATION_BLOCK_HEADER}\n{location_block}".strip()


def normalize_world_payload(payload: dict) -> dict:
    """Normalise a raw world payload dict (from draft or API request)."""
    images = resolve_world_image_fields_from_mapping(payload)
    # Agent 在 images 阶段写 `character_images: {name: url}`. publish_service 之前
    # 的 normalize 把它丢了 → draft.payload 里没这个字段 → 前端无从读到角色头像。
    # 这里同时做两件事：1) 顶层保留 character_images dict（前端兼容入口）
    # 2) 把每个 character 的 avatar 字段从 character_images 里注入（DB 写入路径）
    raw_char_images = payload.get("character_images") or {}
    character_images: dict[str, str] = (
        raw_char_images if isinstance(raw_char_images, dict) else {}
    )

    # v2 agent emits the playable roster as a separate top-level list of
    # {name, role_tag, description}; ``world_characters`` items themselves
    # have no ``playable`` field (Character schema doesn't carry it). Build a
    # name set so we can stamp playable=True on the matching characters.
    raw_playable = payload.get("playable") or []
    playable_names: set[str] = set()
    if isinstance(raw_playable, list):
        for entry in raw_playable:
            if isinstance(entry, dict):
                name = entry.get("name")
                if isinstance(name, str) and name:
                    playable_names.add(name)
            elif isinstance(entry, str) and entry:
                playable_names.add(entry)

    normalized_chars: list[dict] = []
    for wc in payload.get("world_characters") or []:
        name = wc.get("name") if isinstance(wc, dict) else ""
        raw_avatar = wc.get("avatar") if isinstance(wc, dict) else None
        image_avatar = character_images.get(name) if name else None
        avatar_override = None
        if image_avatar and (
            not _is_placeholder_image(image_avatar)
            or not raw_avatar
            or _is_placeholder_image(raw_avatar)
        ):
            avatar_override = image_avatar
        normalized_chars.append(
            _coerce_world_character(
                wc,
                avatar_override=avatar_override,
                playable_override=bool(name) and name in playable_names,
            )
        )

    normalized: dict = {
        "name": payload.get("name", ""),
        "description": payload.get("description", ""),
        "genre": payload.get("genre", ""),
        "era": payload.get("era", ""),
        "difficulty": _coerce_difficulty(payload.get("difficulty")),
        "estimated_time": payload.get("estimated_time", "30-60 min"),
        "base_setting": payload.get("base_setting", ""),
        "free_setting": payload.get("free_setting", ""),
        "cover_image": images["cover_image"],
        "hero_image": images["hero_image"],
        "locations": list(payload.get("locations", [])),
        "world_characters": normalized_chars,
    }
    # v2 fields — only forward when the upstream produced them.
    if payload.get("research_pack") is not None:
        normalized["research_pack"] = payload["research_pack"]
    if character_images:
        normalized["character_images"] = character_images
    # Other v2 fields used by the admin draft editor — keep on JSON column so
    # re-opening a draft restores the full agent output.
    for v2_key in (
        "lore_pack", "shared_events", "relations_pack",
        "events_data", "playable", "quality_warnings",
        "free_start_stages",
    ):
        if payload.get(v2_key) is not None:
            normalized[v2_key] = payload[v2_key]
    return normalized


def normalize_script_payload(payload: dict) -> dict:
    """Normalise a raw script payload dict (from draft or API request)."""
    normalized: dict = {
        "name": payload.get("name", ""),
        "description": payload.get("description", ""),
        "difficulty": payload.get("difficulty", 3),
        "estimated_time": payload.get("estimated_time", "30-60 min"),
        "script_setting": payload.get("script_setting", ""),
        "script_type": payload.get("script_type", "mystery"),
        "events": list(payload.get("events", [])),
        "clues": dict(payload.get("clues", {})),
        "endings": list(payload.get("endings", [])),
        # WorldCharacter UUID 列表（空 = 放行世界全部可玩角色）。发布期会再按
        # 世界现存可玩角色过滤，见 apply_script_payload。
        "playable_character_ids": [
            str(cid) for cid in (payload.get("playable_character_ids", []) or [])
        ],
    }
    # v2 fields — only forward when the upstream produced them.
    for v2_key in ("events_data", "research_pack", "quality_warnings", "cover_image"):
        if payload.get(v2_key) is not None:
            normalized[v2_key] = payload[v2_key]
    # 剧本外挂角色（反哺）：随剧本走的 NPC，发布时落 Script.local_characters。
    normalized["local_characters"] = list(payload.get("local_characters", []) or [])
    return normalized


# ---------------------------------------------------------------------------
# DB-level apply helpers
# ---------------------------------------------------------------------------


async def apply_world_payload(db: AsyncSession, world: World, payload: dict) -> None:
    """Write normalised *payload* fields onto *world* (in-place, no commit)."""
    images = resolve_world_image_fields_from_mapping(payload)
    world.name = payload["name"]
    world.description = payload["description"]
    world.genre = payload["genre"]
    world.era = payload["era"]
    world.difficulty = payload["difficulty"]
    world.estimated_time = payload["estimated_time"]
    world.base_setting = _compose_world_setting(payload["base_setting"], payload["locations"])
    world.locations_data = payload["locations"]
    world.free_setting = payload["free_setting"] or None
    world.cover_image = images["cover_image"] or world.cover_image
    world.hero_image = images["hero_image"] or world.hero_image

    # v2 rich-content fields. Without these the World row keeps the
    # JSONB columns NULL even though normalize_world_payload preserves
    # them in draft.payload — admin editor / runtime free mode / Tier1
    # all silently see empty content.
    if "events_data" in payload:
        world.events_data = payload["events_data"]
    if "shared_events" in payload:
        world.shared_events = payload["shared_events"]
    if "lore_pack" in payload:
        world.lore_pack = payload["lore_pack"]

    playable_ids: list[str] = []
    name_to_id: dict[str, str] = {}
    existing_characters = (
        await db.execute(select(WorldCharacter).where(WorldCharacter.world_id == world.id))
    ).scalars().all()
    existing_by_name = {character.name: character for character in existing_characters}
    payload_names = {
        str(wc_data.get("name", ""))
        for wc_data in payload.get("world_characters", [])
        if wc_data.get("name")
    }

    character_ids = [character.id for character in existing_characters]
    referenced_character_ids: set[str] = set()
    if character_ids:
        referenced_character_ids = set(
            (
                await db.execute(
                    select(GameSession.character_id).where(
                        GameSession.world_id == world.id,
                        GameSession.character_id.in_(character_ids),
                    )
                )
            ).scalars().all()
        )

    for character in existing_characters:
        if character.name not in payload_names and character.id not in referenced_character_ids:
            await db.delete(character)

    for wc_data in payload.get("world_characters", []):
        wc = existing_by_name.get(wc_data["name"])
        if wc is None:
            wc = WorldCharacter(world_id=world.id, name=wc_data["name"])
            db.add(wc)
            await db.flush()

        wc.personality = wc_data.get("personality", "")
        wc.voice_style = wc_data.get("voice_style") or None
        wc.secret = wc_data.get("secret")
        wc.knowledge = wc_data.get("knowledge", [])
        wc.schedule = wc_data.get("schedule", {})
        wc.initial_location = wc_data.get("initial_location", "")
        wc.playable = wc_data.get("playable", False)
        wc.description = wc_data.get("description")
        wc.abilities = wc_data.get("abilities", [])
        wc.starting_inventory = wc_data.get("starting_inventory", [])
        wc.avatar = wc_data.get("avatar")
        wc.initial_peer_relations = wc_data.get("initial_peer_relations") or None
        wc.narrative_weight = _derive_narrative_weight(wc_data)
        name_to_id[wc.name] = str(wc.id)
        if wc.playable:
            playable_ids.append(str(wc.id))

    world.free_playable_character_ids = playable_ids

    # 自由模式起点：payload 里的 free_start_stages 是 name-based——因为生成阶段还没有
    # 角色 UUID。这里 upsert 完角色后把角色名解析成现存 WorldCharacter UUID，落成消费侧
    # schema（{"characters": [{"character_id", "stages"}]}）。兼容两代 draft 形状：
    # 新（多弧线角色）{"characters": [{"character_name", "stages"}]} 与旧（单主角）
    # {"protagonist_name", "stages"}。单个角色名解析不到只剔除那一条；全部解析不到
    # 就不动 world.free_start_stages（保住既有 / backfill 数据，避免一次缺字段的
    # re-save 把起点清空）。known_relations 已是 name-based，无需转换。
    fss = payload.get("free_start_stages")
    if isinstance(fss, dict):
        if isinstance(fss.get("characters"), list):
            raw_entries = fss["characters"]
        elif fss.get("stages"):
            raw_entries = [
                {"character_name": fss.get("protagonist_name"), "stages": fss["stages"]}
            ]
        else:
            raw_entries = []
        resolved = []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            char_id = name_to_id.get(str(entry.get("character_name") or ""))
            stages = entry.get("stages")
            # 少于 2 档不成"选择"，与生成侧规则一致
            if char_id and isinstance(stages, list) and len(stages) >= 2:
                resolved.append({"character_id": char_id, "stages": stages})
        if resolved:
            world.free_start_stages = {"characters": resolved}


def apply_script_payload(
    script: Script,
    payload: dict,
    *,
    valid_playable_ids: set[str] | None = None,
) -> None:
    """Write normalised *payload* fields onto *script* (in-place, no commit).

    *valid_playable_ids* — when provided, ``playable_character_ids`` is filtered
    down to ids that still exist as a playable WorldCharacter in the target
    world (anti-corruption: a character may have been deleted or flipped
    non-playable since the draft was generated). When ``None`` the list is
    written as-is. Empty result = allow-all at runtime.
    """
    script.name = payload["name"]
    script.description = payload["description"]
    script.difficulty = payload["difficulty"]
    script.estimated_time = payload["estimated_time"]
    script.script_setting = payload["script_setting"]
    script.script_type = payload.get("script_type", "mystery")
    script.events_data = payload["events"]
    script.clues_data = payload["clues"]
    script.endings_data = payload["endings"]
    # 剧本外挂角色（反哺）：随剧本走，不触及 world_characters。
    script.local_characters = list(payload.get("local_characters", []) or [])
    if payload.get("cover_image"):
        script.cover_image = payload["cover_image"]

    raw_ids = [str(cid) for cid in (payload.get("playable_character_ids", []) or [])]
    if valid_playable_ids is not None:
        raw_ids = [cid for cid in raw_ids if cid in valid_playable_ids]
    # 去重保序
    deduped: list[str] = []
    for cid in raw_ids:
        if cid not in deduped:
            deduped.append(cid)
    script.playable_character_ids = deduped


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def _load_owned_world_draft(
    db: AsyncSession, *, draft_id: str, actor_user_id: str
) -> WorldDraft:
    draft = (
        await db.execute(select(WorldDraft).where(WorldDraft.id == draft_id))
    ).scalar_one_or_none()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")
    if draft.created_by_user_id != actor_user_id:
        raise PermissionError(
            f"User {actor_user_id} cannot act on draft owned by {draft.created_by_user_id}"
        )
    return draft


async def _materialize_world_draft(
    db: AsyncSession, draft: WorldDraft, *, target_status: ContentStatus
) -> World:
    """Create or update the World row from *draft* and set it to *target_status*.

    Shared by ``save_world_as_private`` (target PRIVATE) and
    ``publish_world_draft`` (target PUBLISHED/SUBMITTED). Does not commit —
    the caller owns the transaction boundary.
    """
    payload = normalize_world_payload(draft.payload)

    # Strict schema gate: reject content that would crash at runtime. Runs for
    # private saves too — a private world must be playable by its owner.
    validate_world_payload({
        "name": payload.get("name", ""),
        "base_setting": payload.get("base_setting", ""),
        "free_setting": payload.get("free_setting", "") or "",
    })

    if draft.world_id:
        # Update existing world row.
        world = (
            await db.execute(select(World).where(World.id == draft.world_id))
        ).scalar_one_or_none()
        if world is None:
            raise ValueError(f"World {draft.world_id} not found")
        current_status = ContentStatus(world.status)
        # Content-only update (status doesn't change) is not a transition —
        # the state machine only validates real state changes.
        if current_status != target_status and not can_transition(current_status, target_status):
            raise ValueError(
                f"Invalid transition for world {world.id}: {current_status} → {target_status}"
            )
        await apply_world_payload(db, world, payload)
        world.status = target_status.value
    else:
        # Create a new world row.
        world = World(
            name=payload["name"],
            description=payload["description"],
            genre=payload["genre"],
            era=payload["era"],
            difficulty=payload["difficulty"],
            estimated_time=payload["estimated_time"],
            base_setting="",
            locations_data=[],
            free_setting=payload.get("free_setting") or None,
            status=target_status.value,
            created_by_user_id=draft.created_by_user_id,
        )
        db.add(world)
        await db.flush()
        draft.world_id = world.id
        await apply_world_payload(db, world, payload)
        world.status = target_status.value  # apply_world_payload does not set status

    return world


async def save_world_as_private(
    db: AsyncSession, *, draft_id: str, actor_user_id: str
) -> World:
    """Materialize a world draft into a PRIVATE (owner-only, playable) World.

    This is the "保存为私有作品" action — it makes the creation playable by its
    owner without exposing it in the public discover feed.
    """
    draft = await _load_owned_world_draft(db, draft_id=draft_id, actor_user_id=actor_user_id)
    # Editing a live published world: keep it live and untouched. The edits stay
    # on the draft (already persisted by the editor's autosave) until the owner
    # re-submits for review — never silently downgrade or bypass review.
    if draft.world_id:
        existing = await db.get(World, draft.world_id)
        if existing is not None and existing.status == ContentStatus.PUBLISHED.value:
            await db.commit()
            await db.refresh(existing)
            return existing
    world = await _materialize_world_draft(db, draft, target_status=ContentStatus.PRIVATE)
    await db.commit()
    await db.refresh(world)
    return world


async def publish_world_draft(
    db: AsyncSession,
    *,
    draft_id: str,
    actor_user_id: str,
    audit_enabled: bool = False,
) -> World:
    """Publish a world draft to the public feed.  Actor must be the draft owner.

    Computes the target status (PUBLISHED, or SUBMITTED when audit is enabled),
    then materializes the draft onto the World row.
    """
    draft = await _load_owned_world_draft(db, draft_id=draft_id, actor_user_id=actor_user_id)
    target_status = next_status_on_publish(audit_enabled=audit_enabled)
    world = await _materialize_world_draft(db, draft, target_status=target_status)
    await db.commit()
    await db.refresh(world)
    return world


async def withdraw_world(
    db: AsyncSession,
    *,
    world_id: str,
    actor_user_id: str,
    by_admin: bool = False,
) -> World:
    """Withdraw a published world.

    Owner withdraw → PRIVATE (back to the private library).  Admin withdraw →
    WITHDRAWN (terminal; owner cannot self-recover).
    """
    world = (
        await db.execute(select(World).where(World.id == world_id))
    ).scalar_one_or_none()
    if not world:
        raise ValueError(f"World {world_id} not found")
    if not by_admin and world.created_by_user_id != actor_user_id:
        raise PermissionError(
            f"User {actor_user_id} cannot withdraw world owned by {world.created_by_user_id}"
        )

    target = next_status_on_withdraw(by_admin=by_admin)
    current = ContentStatus(world.status)
    if not can_transition(current, target):
        raise ValueError(f"Invalid withdraw: {current} → {target}")

    world.status = target.value

    # 连锁下架：世界下架时，配下「已发布」剧本跟随同一目标态一并下线，避免
    # 出现「世界已下架但剧本仍是已发布」的矛盾态（admin→WITHDRAWN 终态；
    # owner→PRIVATE 回退）。PUBLISHED→WITHDRAWN / PUBLISHED→PRIVATE 都是合法
    # 迁移，所以只需扫 published 剧本。剧本不单独发通知——世界下架通知已覆盖。
    cascaded_scripts = (
        await db.execute(
            select(Script).where(
                Script.world_id == world.id,
                Script.status == ContentStatus.PUBLISHED.value,
            )
        )
    ).scalars().all()
    for script in cascaded_scripts:
        script.status = target.value
        script.is_published = False

    if by_admin:
        await ns.notify(
            db,
            user_id=world.created_by_user_id,
            type="content_takedown",
            title=f"《{world.name}》已被下架",
            body="你的世界已被管理员下架，如有疑问可联系我们。",
            link="/workshop",
            payload={"kind": "world", "target_id": str(world.id)},
        )
    await db.commit()
    await db.refresh(world)
    return world


async def _load_owned_script_draft(
    db: AsyncSession, *, draft_id: str, actor_user_id: str
) -> ScriptDraft:
    draft = (
        await db.execute(select(ScriptDraft).where(ScriptDraft.id == draft_id))
    ).scalar_one_or_none()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")
    if draft.created_by_user_id != actor_user_id:
        raise PermissionError(
            f"User {actor_user_id} cannot act on draft owned by {draft.created_by_user_id}"
        )
    return draft


async def _materialize_script_draft(
    db: AsyncSession,
    draft: ScriptDraft,
    *,
    target_status: ContentStatus,
    run_semantic_review: bool,
) -> Script:
    """Create or update the Script row from *draft* and set it to *target_status*.

    Shared by ``save_script_as_private`` (target PRIVATE) and
    ``publish_script_draft`` (target PUBLISHED/SUBMITTED). Schema + cross-artifact
    validation run for both (a private script must be playable by its owner);
    the expensive semantic LLM review only runs when *run_semantic_review* is
    set (i.e. when going public). Does not commit.
    """
    payload = normalize_script_payload(draft.payload)

    # Strict schema gate: reject content that would crash at runtime.
    # events_data is the v2 field; legacy `events` lacks runtime structure.
    validate_script_payload({
        "name": payload.get("name", ""),
        "script_setting": payload.get("script_setting", ""),
        "script_type": payload.get("script_type", "mystery"),
        "events_data": payload.get("events_data") or payload.get("events") or [],
        "endings_data": payload.get("endings") or [],
    })

    # Cross-artifact integrity: events ↔ characters, endings ↔ clues. Schema
    # validation only sees one artifact at a time and misses drift like an
    # event referencing an NPC absent from the roster.
    valid_playable_ids: set[str] | None = None
    world_row = await db.get(World, draft.world_id)
    if world_row is not None:
        world_chars = (
            await db.execute(
                select(WorldCharacter).where(WorldCharacter.world_id == world_row.id)
            )
        ).scalars().all()
        # 发布期世界现存的可玩角色 id 集合，用来过滤剧本可玩名单中已失效/已转 NPC 的 id。
        valid_playable_ids = {str(c.id) for c in world_chars if c.playable}
        # 有效角色命名空间 = 世界角色 ∪ 剧本外挂角色（反哺）。外挂角色随剧本走、
        # 不入 world_characters，但事件可以引用它们，所以校验时要并进世界视图。
        local_chars = payload.get("local_characters") or []
        world_view = {
            "characters": [{"name": c.name} for c in world_chars]
            + [{"name": lc.get("name")} for lc in local_chars if isinstance(lc, dict) and lc.get("name")],
            "events_data": world_row.events_data or [],
        }
        script_view = {
            "events_data": payload.get("events_data") or payload.get("events") or [],
            "endings_data": payload.get("endings") or [],
        }
        validate_cross_artifact(world_view, script_view)

        # Semantic review — warn-only, BUGS #24. Opt-in: needs
        # settings.semantic_review_enabled + a bound admin_generation slot.
        # Never raises; any LLM/runtime failure is swallowed and logged.
        if run_semantic_review and settings.semantic_review_enabled:
            try:
                from services.model_management import resolve_slot_router
                from services.semantic_review import check_semantic_consistency

                router = await resolve_slot_router(db, "admin_generation")
                if router is not None:
                    issues = await check_semantic_consistency(world_view, script_view, router)
                    if issues:
                        publish_logger.warning(
                            "publish.semantic_issues",
                            draft_id=str(draft.id),
                            world_id=str(world_row.id),
                            issues=issues,
                        )
                        # Preserve on draft.payload so admin editor can show
                        # them on the next draft revision.
                        existing = list(payload.get("quality_warnings") or [])
                        payload["quality_warnings"] = existing + [
                            {"category": "semantic", "message": i} for i in issues
                        ]
            except Exception:  # noqa: BLE001 — never block publish on review failures.
                publish_logger.warning("publish.semantic_review_failed", exc_info=True)

    if draft.script_id:
        # Update existing script row.
        script = (
            await db.execute(select(Script).where(Script.id == draft.script_id))
        ).scalar_one_or_none()
        if script is None:
            raise ValueError(f"Script {draft.script_id} not found")
        current_status = ContentStatus(script.status)
        # Content-only update (status doesn't change) is not a transition —
        # the state machine only validates real state changes.
        if current_status != target_status and not can_transition(current_status, target_status):
            raise ValueError(
                f"Invalid transition for script {script.id}: {current_status} → {target_status}"
            )
        apply_script_payload(script, payload, valid_playable_ids=valid_playable_ids)
        script.status = target_status.value
        script.is_published = target_status == ContentStatus.PUBLISHED
    else:
        # Create a new script row.
        script = Script(
            world_id=draft.world_id,
            name="",
            description="",
            status=target_status.value,
            is_published=target_status == ContentStatus.PUBLISHED,
            created_by_user_id=draft.created_by_user_id,
        )
        db.add(script)
        await db.flush()
        draft.script_id = script.id
        apply_script_payload(script, payload, valid_playable_ids=valid_playable_ids)
        script.status = target_status.value
        script.is_published = target_status == ContentStatus.PUBLISHED

    # Sync endings → Ending table. Runtime free-mode (game_service.py:764)
    # and admin tooling read Ending rows by world_id; without this sync the
    # table stays empty for any world generated through the pipeline (only
    # seeds.seed populates it). Wipe+repopulate keeps the table in sync with
    # the latest script — current assumption is one script per world.
    await _sync_endings_table(db, world_id=draft.world_id, endings=payload.get("endings") or [])

    return script


async def save_script_as_private(
    db: AsyncSession, *, draft_id: str, actor_user_id: str
) -> Script:
    """Materialize a script draft into a PRIVATE (owner-only, playable) Script."""
    draft = await _load_owned_script_draft(db, draft_id=draft_id, actor_user_id=actor_user_id)
    # Editing a live published script: keep it live (see save_world_as_private).
    if draft.script_id:
        existing = await db.get(Script, draft.script_id)
        if existing is not None and existing.status == ContentStatus.PUBLISHED.value:
            await db.commit()
            await db.refresh(existing)
            return existing
    script = await _materialize_script_draft(
        db, draft, target_status=ContentStatus.PRIVATE, run_semantic_review=False
    )
    await db.commit()
    await db.refresh(script)
    return script


async def publish_script_draft(
    db: AsyncSession,
    *,
    draft_id: str,
    actor_user_id: str,
    audit_enabled: bool = False,
) -> Script:
    """Publish a script draft to the public feed.  Actor must be the draft owner."""
    draft = await _load_owned_script_draft(db, draft_id=draft_id, actor_user_id=actor_user_id)
    target_status = next_status_on_publish(audit_enabled=audit_enabled)
    script = await _materialize_script_draft(
        db, draft, target_status=target_status, run_semantic_review=True
    )
    await db.commit()
    await db.refresh(script)
    return script


async def _sync_endings_table(db: AsyncSession, *, world_id: str, endings: list) -> None:
    """Replace all Ending rows for world_id with the supplied list."""
    await db.execute(sa_delete(Ending).where(Ending.world_id == world_id))
    for ending in endings:
        if not isinstance(ending, dict) or not ending.get("title"):
            continue
        db.add(
            Ending(
                world_id=world_id,
                ending_type=ending.get("ending_type", "normal") or "normal",
                title=ending["title"],
                description=ending.get("description") or "",
                priority=int(ending.get("priority", 5) or 5),
                hard_conditions=ending.get("hard_conditions"),
                soft_conditions=ending.get("soft_conditions"),
                mode=ending.get("mode", "any") or "any",
                cover_image=ending.get("cover_image"),
            )
        )
    await db.flush()


async def withdraw_script(
    db: AsyncSession,
    *,
    script_id: str,
    actor_user_id: str,
    by_admin: bool = False,
) -> Script:
    """Withdraw a published script.

    Owner withdraw → PRIVATE.  Admin withdraw → WITHDRAWN (terminal).
    """
    script = (
        await db.execute(select(Script).where(Script.id == script_id))
    ).scalar_one_or_none()
    if not script:
        raise ValueError(f"Script {script_id} not found")
    if not by_admin and script.created_by_user_id != actor_user_id:
        raise PermissionError(
            f"User {actor_user_id} cannot withdraw script owned by {script.created_by_user_id}"
        )

    target = next_status_on_withdraw(by_admin=by_admin)
    current = ContentStatus(script.status)
    if not can_transition(current, target):
        raise ValueError(f"Invalid withdraw: {current} → {target}")

    script.status = target.value
    script.is_published = target == ContentStatus.PUBLISHED
    if by_admin:
        await ns.notify(
            db,
            user_id=script.created_by_user_id,
            type="content_takedown",
            title=f"《{script.name}》已被下架",
            body="你的剧本已被管理员下架，如有疑问可联系我们。",
            link="/workshop",
            payload={"kind": "script", "target_id": str(script.id)},
        )
    await db.commit()
    await db.refresh(script)
    return script


# ---------------------------------------------------------------------------
# Restore (admin un-withdraw) — lifts a takedown back to PUBLISHED. Admin-only;
# the API layer gates this on get_current_admin_user. No ownership check.
# ---------------------------------------------------------------------------


async def restore_world(
    db: AsyncSession,
    *,
    world_id: str,
    actor_user_id: str,
) -> World:
    """Restore a withdrawn world → PUBLISHED (撤销下架，重新上架)."""
    world = (
        await db.execute(select(World).where(World.id == world_id))
    ).scalar_one_or_none()
    if not world:
        raise ValueError(f"World {world_id} not found")

    target = ContentStatus.PUBLISHED
    current = ContentStatus(world.status)
    if not can_transition(current, target):
        raise ValueError(f"Invalid restore: {current} → {target}")

    world.status = target.value
    await ns.notify(
        db,
        user_id=world.created_by_user_id,
        type="content_restored",
        title=f"《{world.name}》已恢复上架",
        body="你的世界已由管理员恢复上架。",
        link="/workshop",
        payload={"kind": "world", "target_id": str(world.id)},
    )
    await db.commit()
    await db.refresh(world)
    return world


async def restore_script(
    db: AsyncSession,
    *,
    script_id: str,
    actor_user_id: str,
) -> Script:
    """Restore a withdrawn script → PUBLISHED.

    Guards on the world being published — a public script under a withdrawn
    world would be inconsistent. Restore the world first.
    """
    script = (
        await db.execute(select(Script).where(Script.id == script_id))
    ).scalar_one_or_none()
    if not script:
        raise ValueError(f"Script {script_id} not found")

    world = await db.get(World, script.world_id)
    if not world or world.status != ContentStatus.PUBLISHED.value:
        raise ValueError("请先恢复所属世界")

    target = ContentStatus.PUBLISHED
    current = ContentStatus(script.status)
    if not can_transition(current, target):
        raise ValueError(f"Invalid restore: {current} → {target}")

    script.status = target.value
    script.is_published = True
    await ns.notify(
        db,
        user_id=script.created_by_user_id,
        type="content_restored",
        title=f"《{script.name}》已恢复上架",
        body="你的剧本已由管理员恢复上架。",
        link="/workshop",
        payload={"kind": "script", "target_id": str(script.id)},
    )
    await db.commit()
    await db.refresh(script)
    return script


# ---------------------------------------------------------------------------
# Review flow (P2) — submit / withdraw-submission (owner) + approve / reject (admin)
# Review state lives on the draft, so the live published row is untouched while
# a revision is reviewed.
# ---------------------------------------------------------------------------


async def submit_world_for_review(
    db: AsyncSession, *, draft_id: str, actor_user_id: str
) -> WorldDraft:
    """Owner submits a world draft for admin review. Worlds have no dependency."""
    draft = await _load_owned_world_draft(db, draft_id=draft_id, actor_user_id=actor_user_id)
    draft.review_status = "submitted"
    draft.review_note = None
    await db.commit()
    await db.refresh(draft)
    return draft


async def submit_script_for_review(
    db: AsyncSession, *, draft_id: str, actor_user_id: str
) -> ScriptDraft:
    """Owner submits a script draft for review.

    A public script requires a publicly-playable (published) world — otherwise
    players who find the script can't actually enter the world.
    """
    draft = await _load_owned_script_draft(db, draft_id=draft_id, actor_user_id=actor_user_id)
    world = await db.get(World, draft.world_id)
    if world is None or world.status != ContentStatus.PUBLISHED.value:
        raise ValueError("请先发布所属世界，再提交剧本审核")
    draft.review_status = "submitted"
    draft.review_note = None
    await db.commit()
    await db.refresh(draft)
    return draft


async def withdraw_world_submission(
    db: AsyncSession, *, draft_id: str, actor_user_id: str
) -> WorldDraft:
    draft = await _load_owned_world_draft(db, draft_id=draft_id, actor_user_id=actor_user_id)
    draft.review_status = "editing"
    await db.commit()
    await db.refresh(draft)
    return draft


async def withdraw_script_submission(
    db: AsyncSession, *, draft_id: str, actor_user_id: str
) -> ScriptDraft:
    draft = await _load_owned_script_draft(db, draft_id=draft_id, actor_user_id=actor_user_id)
    draft.review_status = "editing"
    await db.commit()
    await db.refresh(draft)
    return draft


async def approve_world_draft(db: AsyncSession, *, draft_id: str) -> World:
    """Admin approves a submitted world draft → materialize + publish."""
    draft = (
        await db.execute(select(WorldDraft).where(WorldDraft.id == draft_id))
    ).scalar_one_or_none()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")
    if draft.review_status != "submitted":
        raise ValueError("草稿不在审核中")
    world = await _materialize_world_draft(db, draft, target_status=ContentStatus.PUBLISHED)
    draft.review_status = "editing"
    draft.review_note = None
    await db.commit()
    await db.refresh(world)
    return world


async def approve_script_draft(db: AsyncSession, *, draft_id: str) -> Script:
    """Admin approves a submitted script draft → materialize + publish.

    Re-checks the world-published dependency in case the world was withdrawn
    after the script was submitted.
    """
    draft = (
        await db.execute(select(ScriptDraft).where(ScriptDraft.id == draft_id))
    ).scalar_one_or_none()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")
    if draft.review_status != "submitted":
        raise ValueError("草稿不在审核中")
    world = await db.get(World, draft.world_id)
    if world is None or world.status != ContentStatus.PUBLISHED.value:
        raise ValueError("所属世界未发布，无法发布剧本")
    script = await _materialize_script_draft(
        db, draft, target_status=ContentStatus.PUBLISHED, run_semantic_review=True
    )
    draft.review_status = "editing"
    draft.review_note = None
    await db.commit()
    await db.refresh(script)
    return script


async def reject_world_draft(db: AsyncSession, *, draft_id: str, note: str | None) -> WorldDraft:
    draft = (
        await db.execute(select(WorldDraft).where(WorldDraft.id == draft_id))
    ).scalar_one_or_none()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")
    if draft.review_status != "submitted":
        raise ValueError("草稿不在审核中")
    draft.review_status = "rejected"
    draft.review_note = note
    await db.commit()
    await db.refresh(draft)
    return draft


async def reject_script_draft(db: AsyncSession, *, draft_id: str, note: str | None) -> ScriptDraft:
    draft = (
        await db.execute(select(ScriptDraft).where(ScriptDraft.id == draft_id))
    ).scalar_one_or_none()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")
    if draft.review_status != "submitted":
        raise ValueError("草稿不在审核中")
    draft.review_status = "rejected"
    draft.review_note = note
    await db.commit()
    await db.refresh(draft)
    return draft
