"""WorldCreator Agent v2 — 完整 12 阶段流水线（spec §12.3 并发图）。

阶段流：
  A  research_pack        （三路并发：admin_note + tavily + ip_probe）
  B  world_base           （单 LLM：name / description / locations / …）
  C1+C2 并发：
    C1  lore_dimensions   （build_lore_dimensions）
    C2  character_roster  （build_character_roster）
  D1+D2 并发（D1 依赖 C1，D2 依赖 C2）：
    D1  lore_pack         （build_lore_pack，内部 4 路并发）
    D2  characters        （build_characters_in_batches，批内 4 路并发）
  E1  shared_events       （依赖 D2 + research_pack）
  E2  relations_pack      （依赖 D2 + E1，纯 Python）
  F   events_data         （依赖 D1 + D2 + E1，内部 3 路并发）
  G   playable            （从 characters 选 is_image_target=true）
  H   critic              （H1 形状校验 + H2 轻 critic 并发 + H3 moderation）
  I   images              （M5 完整接入 Seedream，当前 placeholder）
  J   validating          （汇总 quality_warnings）

SSE 事件格式遵循 generation_feedback.py：
  {"type": "progress"|"warning"|"result"|"done"|"error", "phase": ..., ...}

M5 注：images 阶段目前只赋 placeholder URL，真实 Seedream 接入留给 M5。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Coroutine, TypeVar

from sqlalchemy.ext.asyncio import async_sessionmaker

T = TypeVar("T")

import structlog

from config import settings
from schemas.character_v2 import Character, CharacterRosterEntry
from schemas.events_data import EventDataEntry
from schemas.ip_knowledge_pack import FidelityMode
from schemas.lore_pack import LorePack
from schemas.research_pack import IPCanon, ResearchPack
from schemas.shared_events import RelationsPack, SharedEvent
from services.character_roster_builder import (
    build_character_roster,
    build_characters_in_batches,
)
from services.cover_brief import (
    CharacterCoverBrief,
    CoverBrief,
    EndingCoverBrief,
    build_character_portrait_prompt,
    build_ending_card_prompt,
    build_script_cover_prompt,
    build_world_cover_prompt,
    build_world_hero_prompt,
)
from services.cover_brief_helper import (
    derive_script_cover_helpers,
    derive_world_cover_brief,
)
from services.events_data_builder import build_events_data
from services.generation_feedback import (
    done_event,
    error_event,
    progress_event,
    result_event,
    warning_event,
)
from services.image_storage import (
    IMAGE_PLACEHOLDER_URL,
    get_image_storage,
    make_image_key,
    save_generated_image_result,
)
from services.lore_pack_builder import build_lore_dimensions, build_lore_pack
from services.relations_pack_builder import build_relations_pack
from services.research_pack_builder import (
    _collect_stream_text,
    _extract_json_from_text,
    build_research_pack,
)
from services.shared_events_builder import build_shared_events
from services.world_creator_retry import with_transient_retry
from services.world_critic_service import (
    heavy_critic_characters,
    heavy_critic_playable,
    light_critic_lore,
    heavy_critic_endings,
    light_critic_shared_events,
    validate_world_shape,
)
from services.world_moderation_service import moderate_world_payload

logger = structlog.get_logger()


async def _generate_image_with_fallback(
    image_gen,
    prompt_tiers: list[str],
    *,
    aspect_ratio: str,
    storage,
    storage_key: str,
    log_key: str = "",
    max_attempts: int = 3,
):
    """Generate an image with up to ``max_attempts`` tries before giving up.

    An empty result (endpoint returned no image — typically a moderation block,
    which arrives as HTTP 200 + empty data, NOT an exception) escalates to the
    next prompt tier, e.g. an IP world's direct anchor to 视觉对标. Exceptions
    (429 / network) back off and retry the same tier. Only after all attempts
    are exhausted is it treated as failed and a placeholder returned.

    Returns ``(url, ImageResult)`` on success, ``(IMAGE_PLACEHOLDER_URL, None)``
    on failure.
    """
    if not prompt_tiers:
        return IMAGE_PLACEHOLDER_URL, None
    tier = 0
    for attempt in range(max_attempts):
        prompt = prompt_tiers[min(tier, len(prompt_tiers) - 1)]
        try:
            result = await image_gen.generate_image(prompt, aspect_ratio=aspect_ratio)
            url = await save_generated_image_result(storage, result, storage_key)
            if url and url != IMAGE_PLACEHOLDER_URL:
                return url, result
            logger.warning("image_gen_blocked", key=log_key, tier=tier, attempt=attempt + 1)
            tier += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("image_gen_error", key=log_key, attempt=attempt + 1, error=str(exc))
            await asyncio.sleep(2 * (attempt + 1))
    return IMAGE_PLACEHOLDER_URL, None

PLACEHOLDER_COVER_URL = "/static/placeholder-cover.png"

# Stage index map (used in progress events)
_STAGE_INDEX = {
    "research_pack": 0,
    "ip_research": 1,
    "world_base": 2,
    "lore_dimensions": 3,
    "character_roster": 4,
    "lore_pack": 5,
    "characters": 6,
    "shared_events": 7,
    "relations_pack": 8,
    "events_data": 9,
    "playable": 10,
    "critic": 11,
    "visual_brief": 12,
    "images": 13,
    "validating": 14,
}
TOTAL_STAGES = len(_STAGE_INDEX)

# Script stage index map
_SCRIPT_STAGE_INDEX = {
    "research_pack": 0,
    "script_base": 1,
    "events": 2,
    "endings": 3,
    "playable": 4,
    "critic": 5,
    "script_visual_brief": 6,
    "script_images": 7,
}
_SCRIPT_TOTAL_STAGES = len(_SCRIPT_STAGE_INDEX)


def _stage_failure_warning(
    phase: str, code: str, exc: BaseException, message: str,
) -> dict:
    """Build a uniform SSE warning for a stage that silently fell back.

    Many stages catch broad exceptions and substitute a degraded default
    (empty list, placeholder name, etc.) so the pipeline keeps running.
    Without a warning the admin sees a clean `completed` event and never
    learns the stage failed. This helper produces the warning that pairs
    with the structlog entry already emitted at every fallback site.
    """
    return warning_event(
        phase, code=code,
        message=f"{message}（{type(exc).__name__}）",
        error_type=type(exc).__name__,
        error=str(exc)[:500],
    )


# Fail-fast thresholds. Below these counts the pipeline aborts before
# spending image budget on content that publish_service will reject. Tuned
# from the 2026-05-23 嘉靖宫变前夜 case where 0 characters / partial events
# still got 5 ending images generated.
_MIN_CHARACTERS = 3
_MIN_EVENTS_DATA = 5
_MIN_SCRIPT_ENDINGS = 2  # matches validate_script_payload minItems


_NAME_MAX_CHARS = 16
_NAME_MIN_CHARS = 2
_PLACEHOLDER_NAME = "未命名世界"


def truncate_world_name(raw_name: str) -> str:
    """Length-cap + control-char strip a world name **without** applying the
    description-prefix rejection heuristic.

    Used for cases where we trust the source (IP pack's ip_name, dedicated
    name-only LLM retry output): we just want a clean string of safe length,
    not the suspicion-based rejection logic that ``coerce_world_name``
    applies. Returns _PLACEHOLDER_NAME only if input is empty / too short.
    """
    cleaned = (raw_name or "").replace("\r", " ").replace("\n", " ").strip()
    cleaned = cleaned.rstrip("，。、 ！？!?,. ")
    if len(cleaned) < _NAME_MIN_CHARS:
        return _PLACEHOLDER_NAME
    if len(cleaned) > _NAME_MAX_CHARS:
        cleaned = cleaned[:_NAME_MAX_CHARS].rstrip("，。、 ！？!?,. ")
        if len(cleaned) < _NAME_MIN_CHARS:
            return _PLACEHOLDER_NAME
    return cleaned


def coerce_world_name(raw_name: str, description: str) -> str:
    """Critic + truncator for world.name. BUGS #16.

    Reasoning models occasionally splice the entire description into
    `name`, producing 30-800 char "titles" that wreck nav/hero rendering.
    This is the single fallback for both LLM-success-oversized and LLM-
    exception paths (formerly truncated to 20 and 30 chars respectively,
    inconsistent — fixed here).

    Heuristics:
    - Strip CR/LF and trailing 中/英 punctuation
    - If name reads as a description prefix (substring of description for
      ≥ 6 chars OR contains newline) → reject, fall back to placeholder
    - Cap at _NAME_MAX_CHARS chars
    - Empty / too short → placeholder
    """
    cleaned = (raw_name or "").replace("\r", " ").replace("\n", " ").strip()
    if not cleaned:
        return _PLACEHOLDER_NAME

    # Strip trailing punctuation that often slips in from LLM truncation.
    cleaned = cleaned.rstrip("，。、 ！？!?,. ")

    # Reject if it's a description prefix — the bug signature was
    # name == description[:30].
    desc_norm = (description or "").replace("\n", " ").strip()
    if desc_norm and len(cleaned) >= 6 and desc_norm.startswith(cleaned[:8]):
        # Looks like the LLM dumped the description into name.
        return _PLACEHOLDER_NAME

    if len(cleaned) < _NAME_MIN_CHARS:
        return _PLACEHOLDER_NAME

    if len(cleaned) > _NAME_MAX_CHARS:
        cleaned = cleaned[:_NAME_MAX_CHARS].rstrip("，。、 ！？!?,. ")
        if len(cleaned) < _NAME_MIN_CHARS:
            return _PLACEHOLDER_NAME

    return cleaned


def _check_min_content(
    *, phase: str, count: int, minimum: int, code: str, what: str,
) -> dict | None:
    """Return a `pipeline_aborted_low_content` warning event when count is
    below minimum, else None. Caller is expected to `yield` the warning
    then `return` from the pipeline generator, skipping all downstream
    image/critic stages.
    """
    if count >= minimum:
        return None
    return warning_event(
        phase,
        code=code,
        message=(
            f"{what}少于最小阈值（{count} < {minimum}），"
            "已跳过下游事件/图像/结局生成以节省成本。"
            "建议检查 LLM 输出后重跑。"
        ),
        aborted=True,
    )


# ---------------------------------------------------------------------------
# Ending payload validation
# ---------------------------------------------------------------------------

_ENDING_TYPE_ENUM = {"good", "normal", "bad", "hidden", "timeout"}
_ENDING_REQUIRED = ("ending_type", "title", "description", "soft_conditions", "priority")


def _validate_ending_payload(ending: dict) -> list[str]:
    """Return human-readable issues for a single ending dict; empty list = OK.

    The runtime (engine/ending_system.py) reads ending_type, title, description,
    and soft_conditions; missing any of these makes the ending unusable. Priority
    decides match order. The legacy generator only produced
    name/description/condition/quality — fixed here.
    """
    issues: list[str] = []
    if not isinstance(ending, dict):
        return ["ending is not a dict"]
    for field in _ENDING_REQUIRED:
        if field not in ending or ending.get(field) in (None, ""):
            issues.append(f"missing required field: {field}")
    et = ending.get("ending_type")
    if et and et not in _ENDING_TYPE_ENUM:
        issues.append(f"ending_type {et!r} not in {sorted(_ENDING_TYPE_ENUM)}")
    if "priority" in ending and not isinstance(ending["priority"], int):
        issues.append("priority must be int")
    return issues


# ---------------------------------------------------------------------------
# Player identity validation
# ---------------------------------------------------------------------------

import re as _re

_PLAYER_NAME_RE = _re.compile(r"你叫(?P<name>[一-鿿A-Za-z0-9_·]{2,12})")


def _validate_player_identity_in_setting(
    base_setting: str,
    playable_names: list[str],
) -> list[str]:
    """If base_setting addresses the player by name (你叫 X), X must be in
    the playable name list. Returns human-readable issues; empty = OK.
    """
    issues: list[str] = []
    if not base_setting:
        return issues
    names_in_setting = {m.group("name") for m in _PLAYER_NAME_RE.finditer(base_setting)}
    allowed = set(playable_names)
    for name in names_in_setting:
        if name not in allowed:
            issues.append(
                f"base_setting references player name {name!r} which is not in "
                f"playable roster: {sorted(allowed)}"
            )
    return issues


# ---------------------------------------------------------------------------
# World base prompt
# ---------------------------------------------------------------------------

# Focused name-only prompt for when world_base's name field is rejected and
# we need a clean fallback before giving up to "未命名世界". Cheap (~200 token)
# and runs as a single retry, not a fallback chain.
_WORLD_NAME_RETRY_SYSTEM = """你是中文剧本起名师。
根据给定的世界描述，用 **4-10 个汉字** 生成一个独立、有画面感的世界名。

硬规则：
- 4-10 个汉字（少于 4 字也不能用）
- **不要**把整段描述截断当作名字
- **不要**包含标点
- **不要**返回 JSON、引号、解释；只返回名字本身一行
- 名字应该是世界的**主题/氛围**，不是地名罗列

示例：
描述：「民国 1934 年上海法租界，霞飞路深处一栋叫『夜行馆』的私人会所...」
返回：夜行馆疑云

描述：「现代都市表层之下的一家『记忆典当行』，老板娘可以收购顾客的某段记忆...」
返回：记忆典当行"""


_WORLD_BASE_SYSTEM = """你是一个互动叙事世界设计师。
根据给定的世界描述、题材、时代和 IP 信息，构建世界的核心框架。

输出严格 JSON，格式：
{
  "name": "世界名称（4-12 字）",
  "description": "世界一段简洁描述（100-200字）",
  "genre": "题材",
  "era": "时代",
  "difficulty": "easy|medium|hard",
  "estimated_time": "预计游玩时长（如 2-4小时）",
  "base_setting": "剧本模式世界背景（详细，300-500字）",
  "free_setting": "自由模式世界背景（侧重开放探索，200-300字）",
  "locations": [
    {"name": "地点名", "description": "地点简介（1-2句）"}
  ]
}

要求：
- **name 字段是硬约束：必须独立精炼，4-12 个汉字，禁止超过 20 字，禁止把整段描述当作 name**
- **locations 必须 3-8 个，不可空数组**
- base_setting 和 free_setting 可共享世界观，但各有侧重
- **不要**在 base_setting / free_setting 中给玩家起具体的名字（例如"你叫 XXX"）。
  玩家身份由后续 playable 阶段确定，世界设定只描述背景与环境。
- 只输出 JSON，不含任何解释文字
"""


class WorldCreatorAgentV2:
    """v2 world creation entry point — complete 12-stage pipeline.

    Dependencies mirror WorldCreatorAgent attributes so generation_task_service
    can share them via the v1 factory without changing constructor signature.
    """

    def __init__(
        self,
        *,
        llm: Any,
        image_gen: Any,
        broker: Any,
        task_service: Any | None = None,
        task_id: str | None = None,
        session_factory: async_sessionmaker | None = None,
    ) -> None:
        self.llm = llm
        self.image_gen = image_gen
        self.broker = broker
        self.task_service = task_service
        self.task_id = task_id
        self.session_factory = session_factory

    # =========================================================================
    # Public entry point
    # =========================================================================

    async def create_world(
        self,
        description: str,
        genre: str = "",
        era: str = "",
        *,
        skip_ip_recognition: bool = False,
        pre_recognition: "Any | None" = None,
        fidelity_mode: FidelityMode = "none",
        draft_id: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        """Run the full 12-stage world creation pipeline, yielding SSE events.

        T4 plumbing (IP fidelity engine):
            skip_ip_recognition  — phase_b 已经在 phase_a 跑过 Stage 0，
                                   下游 IP research 阶段（T7）会用此 flag 跳过
                                   重复识别。Phase 1 仅做存储，下游消费在 T7。
            pre_recognition      — phase_a 产出的 IPRecognition，T7 使用。
            fidelity_mode        — 'strict' / 'loose' / 'none'，T8 接入下游
                                   prompt 时使用。
        """
        global_start = time.monotonic()
        all_warnings: list[str] = []

        # T4 plumbing: store on self so downstream IP research (T7) and
        # prompt-building stages (T8) can consume these values. Phase 1 only
        # wires the storage; the legacy research_pack path still runs.
        self._fidelity_mode: FidelityMode = fidelity_mode
        self._pre_recognition = pre_recognition
        self._skip_ip_recognition: bool = bool(skip_ip_recognition)
        self._draft_id: str | None = draft_id
        self._last_ip_pack = None
        # Per-call dict for inner helpers (those that return data instead of
        # yielding events) to report back swallowed exceptions; the outer
        # generator drains it after each helper call and emits SSE warnings.
        self._stage_errors: dict[str, BaseException] = {}

        # ---- Stage A: research_pack ----
        research_pack = ResearchPack(summary="", passages=[], ip_canon=IPCanon())
        async for ev in self._run_research_pack(description):
            yield ev
        research_pack = self._last_research_pack  # type: ignore[assignment]
        ip_canon = research_pack.ip_canon

        # ---- Stage A+: ip_research (T7) ----
        # When fidelity_mode != "none" AND pre_recognition.kind in (known_ip, hybrid),
        # build the IPKnowledgePack and persist it. Otherwise emit a skipped event so
        # the stage index stays contiguous for the UI.
        async for ev in self._run_ip_research():
            yield ev

        # ---- Stage B: world_base ----
        async for ev in self._run_world_base(description, genre, era, research_pack):
            yield ev
        world_base = self._last_world_base  # type: ignore[assignment]
        locations = world_base.get("locations", [])

        # ---- Stage C1+C2: lore_dimensions || character_roster ----
        async for ev in self._run_c1_c2_concurrent(
            description, genre, era, ip_canon, locations, research_pack
        ):
            yield ev
        lore_dimensions = self._last_lore_dimensions  # type: ignore[assignment]
        roster = self._last_roster  # type: ignore[assignment]

        # ---- Stage D1+D2: lore_pack || characters ----
        async for ev in self._run_d1_d2_concurrent(
            description, ip_canon, lore_dimensions, roster, locations, research_pack
        ):
            yield ev
        lore_pack = self._last_lore_pack  # type: ignore[assignment]
        characters = self._last_characters  # type: ignore[assignment]

        # Fail-fast: roster below publishable minimum → skip shared_events,
        # events_data, playable, critic, images. Was the 嘉靖宫变前夜
        # failure mode where 0 chars still triggered 5 ending image gens.
        warning = _check_min_content(
            phase="character_roster",
            count=len(characters or []),
            minimum=_MIN_CHARACTERS,
            code="character_count_below_minimum",
            what="角色数量",
        )
        if warning is not None:
            logger.warning(
                "pipeline_aborted_low_content",
                stage="character_roster",
                count=len(characters or []),
                minimum=_MIN_CHARACTERS,
            )
            yield warning
            yield error_event(
                message=warning["message"],
                code="pipeline_aborted_low_content",
                phase="character_roster",
            )
            return

        # ---- Stage E1: shared_events ----
        async for ev in self._run_shared_events(description, ip_canon, characters, research_pack):
            yield ev
        shared_events = self._last_shared_events  # type: ignore[assignment]

        # ---- Stage E2: relations_pack ----
        async for ev in self._run_relations_pack(characters, shared_events):
            yield ev
        relations_pack = self._last_relations_pack  # type: ignore[assignment]

        # ---- Stage F: events_data ----
        async for ev in self._run_events_data(
            description, ip_canon, characters, locations, shared_events, lore_pack
        ):
            yield ev
        events_data = self._last_events_data  # type: ignore[assignment]

        # Fail-fast: events_data below publishable minimum → skip
        # playable/critic/cover/hero/endings image generation.
        warning = _check_min_content(
            phase="events_data",
            count=len(events_data or []),
            minimum=_MIN_EVENTS_DATA,
            code="events_count_below_minimum",
            what="事件数量",
        )
        if warning is not None:
            logger.warning(
                "pipeline_aborted_low_content",
                stage="events_data",
                count=len(events_data or []),
                minimum=_MIN_EVENTS_DATA,
            )
            yield warning
            yield error_event(
                message=warning["message"],
                code="pipeline_aborted_low_content",
                phase="events_data",
            )
            return

        # ---- Stage G: playable ----
        async for ev in self._run_playable(characters):
            yield ev
        playable = self._last_playable  # type: ignore[assignment]

        # ---- Cross-validate: base_setting must not reference unknown player names ----
        identity_issues = _validate_player_identity_in_setting(
            world_base.get("base_setting", "") or "",
            [p.get("name", "") for p in (playable or [])],
        )
        if identity_issues:
            logger.warning(
                "playable_identity_mismatch",
                issues=identity_issues,
            )
            for issue in identity_issues:
                all_warnings.append(f"[playable_identity_mismatch] {issue}")
            yield warning_event(
                "playable",
                code="playable_identity_mismatch",
                message=identity_issues[0],
            )

        # ---- Build working payload (needed for critic + moderation) ----
        working_payload = self._build_working_payload(
            world_base=world_base,
            characters=characters,
            playable=playable,
            lore_pack=lore_pack,
            shared_events=shared_events,
            events_data=events_data,
            research_pack=research_pack,
            relations_pack=relations_pack,
        )

        # ---- Stage H: critic (H1 shape + H2 light critic + H2.5 heavy critic + H3 moderation) ----
        async for ev in self._run_critic(
            working_payload, lore_pack, shared_events, ip_canon, all_warnings,
            characters=characters, description=description,
        ):
            yield ev

        # ---- Stage I-pre: visual_brief (one LLM call → structured English brief) ----
        async for ev in self._run_visual_brief_stage(payload=working_payload, characters=characters):
            yield ev

        # ---- Stage I: images (1 hero @21:9 + N portraits @2:3 + server-cropped 3:2 cover) ----
        async for ev in self._run_images(working_payload, characters):
            yield ev

        # ---- Stage J: validating ----
        async for ev in self._run_validating(working_payload, all_warnings):
            yield ev

        # ---- Final result + done ----
        working_payload["quality_warnings"] = all_warnings
        yield result_event({**working_payload})
        yield done_event()

        logger.info(
            "world_creator_v2_done",
            duration_s=round(time.monotonic() - global_start, 2),
        )

    # =========================================================================
    # Stage A: research_pack
    # =========================================================================

    async def _run_research_pack(self, description: str) -> AsyncIterator[dict]:
        start = time.monotonic()
        yield progress_event(
            "research_pack", "started",
            stage_index=_STAGE_INDEX["research_pack"],
            total_stages=TOTAL_STAGES,
        )
        pack = ResearchPack(summary="", passages=[], ip_canon=IPCanon())
        work = with_transient_retry(
            lambda: build_research_pack(
                description=description,
                broker=self.broker,
                llm_router=self.llm,
                max_passages=settings.research_pack_max_passages,
                max_passage_chars=settings.research_pack_max_passage_chars,
            ),
            max_attempts=3,
            on_retry=self._make_retry_logger("research_pack"),
        )
        try:
            async for item in self._run_with_pulse("research_pack", work):
                if isinstance(item, tuple) and item[0] == "result":
                    pack = item[1] or ResearchPack(summary="", passages=[], ip_canon=IPCanon())
                else:
                    yield item
        except Exception as exc:  # noqa: BLE001
            logger.warning("research_pack_failed", error=str(exc))
            yield _stage_failure_warning(
                "research_pack", "research_pack_failed", exc,
                "研究素材采集失败，已退回空 research_pack；下游不会有联网素材，IP/历史细节会受影响",
            )
            pack = ResearchPack(summary="", passages=[], ip_canon=IPCanon())

        self._last_research_pack = pack
        await self._record_intermediate("research_pack", pack.model_dump())

        yield progress_event(
            "research_pack", "completed",
            stage_index=_STAGE_INDEX["research_pack"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            passages=len(pack.passages),
            canonical_names=len(pack.ip_canon.canonical_names),
            artifact_count=len(pack.passages),
            sample=list((pack.ip_canon.canonical_names or pack.ip_canon.canonical_places or [])[:3]),
        )

    # =========================================================================
    # Stage A+: ip_research (T7)
    # =========================================================================

    async def _run_ip_research(self) -> AsyncIterator[dict]:
        """Stage A+: build and persist the IP Knowledge Pack for this draft.

        Skipped when fidelity_mode == "none" or pre_recognition is missing/original.

        The IP pack is committed in its own DB session (independent of the rest of the
        pipeline). This is intentional: even if a downstream stage like world_base or
        characters fails, the pack persists for debugging and re-runs. Consumers should
        not assume an IP pack row implies a successful world generation.
        """
        from services.ip_pack_storage import save_ip_knowledge_pack
        from services.ip_research_pipeline import (
            IPPackUnderfilledError,
            build_ip_knowledge_pack,
        )

        fidelity = getattr(self, "_fidelity_mode", "none")
        rec = getattr(self, "_pre_recognition", None)
        draft_id = getattr(self, "_draft_id", None)

        rec_kind = getattr(rec, "kind", None) if rec is not None else None
        if fidelity == "none" or rec_kind not in ("known_ip", "hybrid"):
            self._last_ip_pack = None
            yield progress_event(
                "ip_research", "completed",
                stage_index=_STAGE_INDEX["ip_research"],
                total_stages=TOTAL_STAGES,
                duration_ms=0,
                skipped=True,
                reason="no_ip_or_original",
                ip_name=None,
                characters=0,
                places=0,
                must_have_characters=0,
                passages=0,
            )
            return

        start = time.monotonic()
        ip_name = getattr(rec, "ip_name", None)
        yield progress_event(
            "ip_research", "started",
            message=(
                f"正在查阅《{ip_name}》的原作资料（联网检索 + 抽取角色 / 地点 / 关键设定）…"
                if ip_name
                else "正在抽取 IP 知识（联网检索 + 角色 / 地点 / 关键设定）…"
            ),
            stage_index=_STAGE_INDEX["ip_research"],
            total_stages=TOTAL_STAGES,
            ip_name=ip_name,
            fidelity_mode=fidelity,
        )

        # Resolve tavily via the broker (v1 agent stores it there; v2 has no
        # direct tavily attribute).
        tavily = getattr(self, "tavily", None) or getattr(self.broker, "tavily", None)

        # Grok provider for web_search (Phase 2.1 — primary IP research source).
        grok_provider = None
        try:
            from llm.grok import GrokProvider
            grok_provider = GrokProvider()
        except Exception as exc:  # noqa: BLE001
            logger.warning("grok_provider_init_failed", error=str(exc))

        # Wrap the (potentially 30+s) IP knowledge build in a pulse loop so the
        # UI keeps showing "still working" instead of looking frozen on
        # "started" until completed lands.
        pack = None
        underfill_error: IPPackUnderfilledError | None = None
        build_error: Exception | None = None
        try:
            work = build_ip_knowledge_pack(
                rec=rec,
                fidelity_mode=fidelity,
                llm_router=self.llm,
                tavily=tavily,
                grok_provider=grok_provider,
            )
            async for item in self._run_with_pulse("ip_research", work):
                if isinstance(item, tuple) and item[0] == "result":
                    pack = item[1]
                elif isinstance(item, dict):
                    item.setdefault("message", "仍在抽取 IP 知识，已联网检索中…")
                    yield item
        except IPPackUnderfilledError as exc:
            logger.warning(
                "ip_research_underfilled",
                ip_name=exc.ip_name,
                character_count=exc.character_count,
                summary_len=exc.summary_len,
            )
            underfill_error = exc
            pack = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("ip_research_build_failed", error=str(exc))
            build_error = exc
            pack = None

        # Emit a user-visible SSE warning when the pack is underfilled / missing
        # so admin sees the strict-fidelity degradation instead of getting a
        # silent free-styled world later.
        if underfill_error is not None:
            yield warning_event(
                "ip_research",
                code="ip_pack_underfilled",
                message=(
                    f"《{underfill_error.ip_name}》的原作锚点抽取不足"
                    f"（characters={underfill_error.character_count}）；"
                    "下游 strict 约束将退化，建议改 loose 或重跑。"
                ),
                ip_name=underfill_error.ip_name,
                character_count=underfill_error.character_count,
            )
        elif build_error is not None:
            # Generic build failure used to be swallowed silently — admin saw
            # "completed" with no pack and the world was generated with no canon
            # anchors. Surface it so they know strict-fidelity was bypassed.
            yield warning_event(
                "ip_research",
                code="ip_pack_build_failed",
                message=(
                    f"《{ip_name}》IP 知识抽取异常（{type(build_error).__name__}）；"
                    "下游 strict 约束已绕过，世界将退化为自由生成，建议重跑。"
                ),
                ip_name=ip_name,
                error_type=type(build_error).__name__,
                error=str(build_error)[:500],
            )
        elif pack is not None and len(pack.must_have_character_names()) == 0:
            # Pack exists but has zero must-have anchors — strict mode becomes a
            # no-op silently in character_roster_builder. Surface this to admin.
            yield warning_event(
                "ip_research",
                code="ip_pack_no_must_have",
                message=(
                    f"《{pack.ip_name}》抽到 {len(pack.characters)} 个角色但 must_have 全为 false；"
                    "strict 约束将无法强制注入。"
                ),
                ip_name=pack.ip_name,
                character_count=len(pack.characters),
            )

        # Persist when we got a non-empty pack and have a draft to bind it to.
        # Use the injected session_factory when available so tests and callers
        # that supply their own factory write to the correct database instead of
        # the global module-level default.
        if pack is not None and pack.ip_name and draft_id:
            try:
                from database import async_session as default_session_factory

                session_factory = self.session_factory or default_session_factory
                async with session_factory() as ip_db:
                    await save_ip_knowledge_pack(ip_db, pack, draft_id=draft_id)
                    await ip_db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("ip_research_persist_failed", error=str(exc))

        self._last_ip_pack = pack

        if pack is not None:
            try:
                await self._record_intermediate("ip_research", pack.model_dump())
            except Exception as exc:  # noqa: BLE001
                logger.warning("ip_research_record_intermediate_failed", error=str(exc))

        yield progress_event(
            "ip_research", "completed",
            stage_index=_STAGE_INDEX["ip_research"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            ip_name=pack.ip_name if pack else None,
            characters=len(pack.characters) if pack else 0,
            places=len(pack.places) if pack else 0,
            must_have_characters=len(pack.must_have_character_names()) if pack else 0,
            passages=len(pack.passages) if pack else 0,
        )

    # =========================================================================
    # Stage B: world_base
    # =========================================================================

    async def _run_world_base(
        self,
        description: str,
        genre: str,
        era: str,
        research_pack: ResearchPack,
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        yield progress_event(
            "world_base", "started",
            stage_index=_STAGE_INDEX["world_base"],
            total_stages=TOTAL_STAGES,
        )

        world_base = await self._generate_world_base(description, genre, era, research_pack)
        if err := self._stage_errors.pop("world_base", None):
            yield _stage_failure_warning(
                "world_base", "world_base_llm_failed", err,
                "世界基础信息生成失败，已用输入文本兜底（世界名/描述/地点为占位值），建议重跑",
            )
        self._last_world_base = world_base
        await self._record_intermediate("world_base", world_base)

        locs = world_base.get("locations", []) or []
        yield progress_event(
            "world_base", "completed",
            stage_index=_STAGE_INDEX["world_base"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            world_name=world_base.get("name", ""),
            location_count=len(locs),
            sample=[
                loc.get("name", "") for loc in locs[:3]
                if isinstance(loc, dict) and loc.get("name")
            ],
        )

    async def _resolve_world_name(
        self,
        *,
        description: str,
        llm_candidate: str,
        ip_pack: Any | None,
        fidelity: str,
    ) -> str:
        """Single source of truth for world.name.

        Two distinct paths because the user-facing expectation differs:

        - **IP world** (``ip_pack`` exists + ``fidelity`` in strict/loose):
          name = the IP's canonical name (e.g. "哈利·波特"). The whole point
          of strict/loose fidelity is to match the original — generating a
          custom subtitle like "禁林谜踪" defeats discoverability when the
          user is searching "哈利波特".

        - **Original world**: trust the world_base LLM call first; if its
          name fails the ``coerce_world_name`` heuristic (description dump
          / too short), retry once with a focused name-only prompt. Only
          fall back to "未命名世界" if both fail. The previous code's
          fallback (``coerce_world_name(description[:20], description)``)
          was a no-op — description[:20] always startswith description,
          so the rejection heuristic always fired.
        """
        # IP path: anchor to canonical IP name. Only length-coerce, no
        # description-prefix rejection (ip_name + description may legitimately
        # share tokens like the IP title).
        if fidelity in ("strict", "loose"):
            ip_name = (getattr(ip_pack, "ip_name", "") or "").strip()
            if not ip_name:
                # Pack may be absent (IP research produced none) but Stage-0
                # recognition still identified the IP — use that canonical
                # name so an IP world keeps its real title instead of an LLM
                # thematic subtitle (e.g. 后宫·甄嬛传 → not 紫禁深宫). 2026-05-31
                rec = getattr(self, "_pre_recognition", None)
                ip_name = (getattr(rec, "ip_name", "") or "").strip() if rec else ""
            if ip_name:
                truncated = truncate_world_name(ip_name)
                if truncated != _PLACEHOLDER_NAME:
                    logger.info("world_name_from_ip", ip_name=ip_name, used=truncated)
                    return truncated

        # Original path 1: trust the LLM's candidate after coercion.
        if llm_candidate:
            coerced = coerce_world_name(llm_candidate, description)
            if coerced != _PLACEHOLDER_NAME:
                if coerced != llm_candidate:
                    logger.info(
                        "world_name_candidate_truncated",
                        original_len=len(llm_candidate),
                        coerced=coerced,
                    )
                return coerced
            logger.info(
                "world_name_candidate_rejected",
                preview=llm_candidate[:60],
            )

        # Original path 2: focused name-only LLM retry.
        try:
            retry_text = await with_transient_retry(
                lambda: _collect_stream_text(
                    self.llm,
                    system=_WORLD_NAME_RETRY_SYSTEM,
                    messages=[{"role": "user", "content": f"世界描述：{description[:600]}"}],
                    max_tokens=200,
                ),
                max_attempts=2,
                on_retry=self._make_retry_logger("world_name_retry"),
            )
            retry_name = (retry_text or "").strip().splitlines()[0].strip() if retry_text else ""
            retry_name = retry_name.strip("「」\"'`* 　").rstrip("，。、 ！？!?,. ")
            if retry_name:
                truncated = truncate_world_name(retry_name)
                if truncated != _PLACEHOLDER_NAME:
                    logger.info("world_name_from_retry", used=truncated)
                    return truncated
        except Exception as exc:  # noqa: BLE001
            logger.warning("world_name_retry_failed", error=str(exc))

        logger.warning("world_name_placeholder_used", description_preview=description[:60])
        return _PLACEHOLDER_NAME

    async def _generate_world_base(
        self,
        description: str,
        genre: str,
        era: str,
        research_pack: "ResearchPack | None" = None,
    ) -> dict:
        """Single LLM call to produce world framework. Falls back to defaults on failure.

        T8: When IPKnowledgePack is available and fidelity_mode is strict/loose, inject
        the pack as hard/soft constraints. The legacy negative-cue placeholders that
        previously surfaced when IP fields were empty have been removed — silence is
        better than a negative hint.
        """
        ip_pack = self._last_ip_pack
        fidelity = self._fidelity_mode

        user_message = (
            f"世界描述：{description}\n"
            f"题材：{genre or '未指定'}\n"
            f"时代：{era or '未指定'}\n"
        )

        # ONLY render IP context when pack exists AND fidelity is non-none
        if ip_pack and fidelity in ("strict", "loose") and ip_pack.summary:
            user_message += f"\n原作摘要：{ip_pack.summary[:1500]}\n"
            must_have_places = ip_pack.must_have_place_names()
            optional_places = [p.name for p in ip_pack.places if not p.must_have]
            if must_have_places:
                if fidelity == "strict":
                    user_message += (
                        f"\n【强约束】locations 必须从以下原作地点中选用，可微调描述但**禁止新增同类地点**：\n"
                        f"必含：{', '.join(must_have_places)}\n"
                    )
                    if optional_places:
                        user_message += f"可选扩展：{', '.join(optional_places)}\n"
                else:  # loose
                    user_message += (
                        f"\n【参考】原作核心地点：{', '.join(must_have_places)}\n"
                        f"建议优先使用，如需扩展可添加。\n"
                    )

        user_message += "\n\n请输出世界核心框架（JSON 格式）。"

        try:
            text = await with_transient_retry(
                lambda: _collect_stream_text(
                    self.llm,
                    system=_WORLD_BASE_SYSTEM,
                    messages=[{"role": "user", "content": user_message}],
                    max_tokens=2048,
                ),
                max_attempts=3,
                on_retry=self._make_retry_logger("world_base"),
            )
            data = _extract_json_from_text(text)
            if data and isinstance(data, dict):
                # Normalize locations to list[dict]
                raw_locs = data.get("locations") or []
                locs: list[dict] = []
                for loc in raw_locs:
                    if isinstance(loc, dict) and loc.get("name"):
                        locs.append({"name": loc["name"], "description": loc.get("description", "")})
                    elif isinstance(loc, str) and loc:
                        locs.append({"name": loc, "description": ""})
                data["locations"] = locs

                # Resolve world.name through the single resolver (IP path or
                # original-with-retry). This replaces the old inline coerce
                # which silently fell through to "未命名世界" whenever the LLM's
                # name was rejected.
                raw_name = str(data.get("name") or "").strip()
                data["name"] = await self._resolve_world_name(
                    description=description,
                    llm_candidate=raw_name,
                    ip_pack=ip_pack,
                    fidelity=fidelity,
                )
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("world_base_llm_failed", error=str(exc))
            self._stage_errors["world_base"] = exc

        # Fallback defaults — world_base LLM failed entirely. Still try the
        # resolver (it'll either use IP name or the dedicated retry) before
        # giving up to placeholder.
        fallback_name = await self._resolve_world_name(
            description=description,
            llm_candidate="",
            ip_pack=ip_pack,
            fidelity=fidelity,
        )
        return {
            "name": fallback_name,
            "description": description,
            "genre": genre or "未指定",
            "era": era or "未指定",
            "difficulty": "medium",
            "estimated_time": "2-4小时",
            "base_setting": description,
            "free_setting": description,
            "locations": [],
        }

    # =========================================================================
    # Stage C1+C2: lore_dimensions || character_roster (concurrent)
    # =========================================================================

    async def _run_c1_c2_concurrent(
        self,
        description: str,
        genre: str,
        era: str,
        ip_canon: IPCanon,
        locations: list[dict],
        research_pack: ResearchPack,
    ) -> AsyncIterator[dict]:
        """Run lore_dimensions and character_roster concurrently, collect events."""
        # Collect events from both concurrently
        c1_events: list[dict] = []
        c2_events: list[dict] = []

        async def collect_c1():
            async for ev in self._run_lore_dimensions(description, genre, era, ip_canon):
                c1_events.append(ev)

        async def collect_c2():
            async for ev in self._run_character_roster(
                description, genre, era, ip_canon, locations, research_pack
            ):
                c2_events.append(ev)

        await asyncio.gather(collect_c1(), collect_c2())

        # Merge events in a sensible order: interleave started events, then completed
        # Simple approach: yield all c1 started first, c2 started, then work, then completed
        for ev in c1_events:
            yield ev
        for ev in c2_events:
            yield ev

    async def _run_lore_dimensions(
        self,
        description: str,
        genre: str,
        era: str,
        ip_canon: IPCanon,
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        yield progress_event(
            "lore_dimensions", "started",
            stage_index=_STAGE_INDEX["lore_dimensions"],
            total_stages=TOTAL_STAGES,
        )
        dims = []
        work = with_transient_retry(
            lambda: build_lore_dimensions(
                description=description,
                genre=genre,
                era=era,
                ip_canon=ip_canon,
                llm_router=self.llm,
                ip_pack=self._last_ip_pack,
                fidelity_mode=self._fidelity_mode,
            ),
            max_attempts=3,
            on_retry=self._make_retry_logger("lore_dimensions"),
        )
        try:
            async for item in self._run_with_pulse("lore_dimensions", work):
                if isinstance(item, tuple) and item[0] == "result":
                    dims = item[1] or []
                else:
                    yield item
        except Exception as exc:  # noqa: BLE001
            logger.warning("lore_dimensions_failed", error=str(exc))
            yield _stage_failure_warning(
                "lore_dimensions", "lore_dimensions_failed", exc,
                "世界维度规划失败，下游 lore_pack 将基于空骨架生成；建议重跑",
            )
            dims = []

        self._last_lore_dimensions = dims
        yield progress_event(
            "lore_dimensions", "completed",
            stage_index=_STAGE_INDEX["lore_dimensions"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            dimension_count=len(dims),
            sample=[d.name for d in dims[:3] if getattr(d, "name", "")],
        )

    async def _run_character_roster(
        self,
        description: str,
        genre: str,
        era: str,
        ip_canon: IPCanon,
        locations: list[dict],
        research_pack: ResearchPack,
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        yield progress_event(
            "character_roster", "started",
            stage_index=_STAGE_INDEX["character_roster"],
            total_stages=TOTAL_STAGES,
        )
        roster: list[CharacterRosterEntry] = []
        work = with_transient_retry(
            lambda: build_character_roster(
                description=description,
                genre=genre,
                era=era,
                ip_canon=ip_canon,
                locations=locations,
                passages=research_pack.passages,
                llm_router=self.llm,
                ip_pack=self._last_ip_pack,
                fidelity_mode=self._fidelity_mode,
            ),
            max_attempts=3,
            on_retry=self._make_retry_logger("character_roster"),
        )
        try:
            async for item in self._run_with_pulse("character_roster", work):
                if isinstance(item, tuple) and item[0] == "result":
                    roster = item[1] or []
                else:
                    yield item
        except Exception as exc:  # noqa: BLE001
            logger.warning("character_roster_failed", error=str(exc))
            yield _stage_failure_warning(
                "character_roster", "character_roster_failed", exc,
                "角色阵容规划失败，下游 characters 阶段没有名册作为锚点；建议重跑",
            )
            roster = []

        self._last_roster = roster
        yield progress_event(
            "character_roster", "completed",
            stage_index=_STAGE_INDEX["character_roster"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            roster_count=len(roster),
            role_count=len(roster),
            sample=[
                r.role_tag or r.name for r in roster[:3]
                if getattr(r, "role_tag", "") or getattr(r, "name", "")
            ],
        )

    # =========================================================================
    # Stage D1+D2: lore_pack || characters (concurrent)
    # =========================================================================

    async def _run_d1_d2_concurrent(
        self,
        description: str,
        ip_canon: IPCanon,
        lore_dimensions: list,
        roster: list[CharacterRosterEntry],
        locations: list[dict],
        research_pack: ResearchPack,
    ) -> AsyncIterator[dict]:
        d1_events: list[dict] = []
        d2_events: list[dict] = []

        async def collect_d1():
            async for ev in self._run_lore_pack(
                description, ip_canon, lore_dimensions, research_pack
            ):
                d1_events.append(ev)

        async def collect_d2():
            async for ev in self._run_characters(
                description, ip_canon, roster, locations, research_pack
            ):
                d2_events.append(ev)

        await asyncio.gather(collect_d1(), collect_d2())

        for ev in d1_events:
            yield ev
        for ev in d2_events:
            yield ev

    async def _run_lore_pack(
        self,
        description: str,
        ip_canon: IPCanon,
        lore_dimensions: list,
        research_pack: ResearchPack,
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        total_dims = len(lore_dimensions) if lore_dimensions else 0
        yield progress_event(
            "lore_pack", "started",
            stage_index=_STAGE_INDEX["lore_pack"],
            total_stages=TOTAL_STAGES,
            subtask_total=total_dims,
        )
        pack = LorePack(dimensions=[])
        try:
            pack = await with_transient_retry(
                lambda: build_lore_pack(
                    dimensions=lore_dimensions,
                    description=description,
                    ip_canon=ip_canon,
                    passages=research_pack.passages,
                    llm_router=self.llm,
                    concurrency=4,
                ),
                max_attempts=3,
                on_retry=self._make_retry_logger("lore_pack"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("lore_pack_failed", error=str(exc))
            yield _stage_failure_warning(
                "lore_pack", "lore_pack_failed", exc,
                "世界设定包生成失败，lore_pack 为空；世界缺少修炼体系/势力/历史等深度设定",
            )
            pack = LorePack(dimensions=[])

        self._last_lore_pack = pack
        await self._record_intermediate("lore_pack", pack.model_dump())

        # Replay subtask events (batch emit after builder completes)
        completed_count = 0
        for i, dim in enumerate(pack.dimensions):
            if dim.content_blocks:
                completed_count += 1
                yield progress_event(
                    "lore_pack", "subtask_completed",
                    subtask_key=f"dim:{dim.key}",
                    subtask_index=completed_count,
                    subtask_total=total_dims,
                    payload_summary={
                        "content_blocks": len(dim.content_blocks),
                        "dim_label": getattr(dim, "name", "") or dim.key,
                    },
                )
            else:
                yield warning_event(
                    "lore_pack", "subtask_failed",
                    subtask_key=f"dim:{dim.key}",
                )

        yield progress_event(
            "lore_pack", "completed",
            stage_index=_STAGE_INDEX["lore_pack"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            dimension_count=len(pack.dimensions),
            sample=[
                getattr(d, "name", "") or d.key for d in pack.dimensions[:3]
                if getattr(d, "name", "") or getattr(d, "key", "")
            ],
        )

    async def _run_characters(
        self,
        description: str,
        ip_canon: IPCanon,
        roster: list[CharacterRosterEntry],
        locations: list[dict],
        research_pack: ResearchPack,
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        total_roster = len(roster) if roster else 0
        yield progress_event(
            "characters", "started",
            stage_index=_STAGE_INDEX["characters"],
            total_stages=TOTAL_STAGES,
            subtask_total=total_roster,
        )
        characters: list[Character] = []
        try:
            characters = await with_transient_retry(
                lambda: build_characters_in_batches(
                    roster=roster,
                    description=description,
                    ip_canon=ip_canon,
                    locations=locations,
                    passages=research_pack.passages,
                    llm_router=self.llm,
                    batch_size=6,
                    concurrency=4,
                    ip_pack=self._last_ip_pack,
                    fidelity_mode=self._fidelity_mode,
                ),
                max_attempts=3,
                on_retry=self._make_retry_logger("characters"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("characters_failed", error=str(exc))
            yield _stage_failure_warning(
                "characters", "characters_failed", exc,
                "角色档案生成失败，世界 0 个角色；这是灾难性失败，强烈建议重跑",
            )
            characters = []

        self._last_characters = characters
        await self._record_intermediate(
            "characters", [c.model_dump() for c in characters]
        )

        # Replay subtask events per character (batch emit after builder completes)
        for i, char in enumerate(characters):
            yield progress_event(
                "characters", "subtask_completed",
                subtask_key=f"char:{char.name}",
                subtask_index=i + 1,
                subtask_total=total_roster,
                payload_summary={"name": char.name, "role_tag": char.role_tag or ""},
            )

        yield progress_event(
            "characters", "completed",
            stage_index=_STAGE_INDEX["characters"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            character_count=len(characters),
            sample=[c.name for c in characters[:3] if c.name],
        )

    # =========================================================================
    # Stage E1: shared_events
    # =========================================================================

    async def _run_shared_events(
        self,
        description: str,
        ip_canon: IPCanon,
        characters: list[Character],
        research_pack: ResearchPack,
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        yield progress_event(
            "shared_events", "started",
            stage_index=_STAGE_INDEX["shared_events"],
            total_stages=TOTAL_STAGES,
        )
        shared_events: list[SharedEvent] = []
        work = with_transient_retry(
            lambda: build_shared_events(
                description=description,
                ip_canon=ip_canon,
                characters=characters,
                passages=research_pack.passages,
                llm_router=self.llm,
                k_target=15,
                k_min=5,
                ip_pack=getattr(self, "_last_ip_pack", None),
                fidelity_mode=getattr(self, "_fidelity_mode", "none"),
            ),
            max_attempts=3,
            on_retry=self._make_retry_logger("shared_events"),
        )
        try:
            async for item in self._run_with_pulse("shared_events", work):
                if isinstance(item, tuple) and item[0] == "result":
                    shared_events = item[1] or []
                else:
                    yield item
        except Exception as exc:  # noqa: BLE001
            logger.warning("shared_events_failed", error=str(exc))
            yield _stage_failure_warning(
                "shared_events", "shared_events_failed", exc,
                "共享历史事件生成失败，世界缺少跨角色因果链；NPC 行为参考会受影响",
            )
            shared_events = []

        self._last_shared_events = shared_events
        await self._record_intermediate(
            "shared_events", [e.model_dump() for e in shared_events]
        )

        yield progress_event(
            "shared_events", "completed",
            stage_index=_STAGE_INDEX["shared_events"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            event_count=len(shared_events),
            sample=[ev.title for ev in shared_events[:2] if getattr(ev, "title", "")],
        )

    # =========================================================================
    # Stage E2: relations_pack (pure Python, instant)
    # =========================================================================

    async def _run_relations_pack(
        self,
        characters: list[Character],
        shared_events: list[SharedEvent],
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        yield progress_event(
            "relations_pack", "started",
            stage_index=_STAGE_INDEX["relations_pack"],
            total_stages=TOTAL_STAGES,
        )
        try:
            pack = build_relations_pack(characters=characters, shared_events=shared_events)
        except Exception as exc:  # noqa: BLE001
            logger.warning("relations_pack_failed", error=str(exc))
            yield _stage_failure_warning(
                "relations_pack", "relations_pack_failed", exc,
                "角色关系网构建失败（纯 Python 阶段，通常是数据形状异常）；NPC 关系字段缺失",
            )
            pack = RelationsPack(relations_by_npc={})

        self._last_relations_pack = pack
        await self._record_intermediate("relations_pack", pack.model_dump())

        edge_count = sum(len(rels) for rels in pack.relations_by_npc.values())
        yield progress_event(
            "relations_pack", "completed",
            stage_index=_STAGE_INDEX["relations_pack"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            npc_count=len(pack.relations_by_npc),
            edge_count=edge_count,
        )

    # =========================================================================
    # Stage F: events_data
    # =========================================================================

    async def _run_events_data(
        self,
        description: str,
        ip_canon: IPCanon,
        characters: list[Character],
        locations: list[dict],
        shared_events: list[SharedEvent],
        lore_pack: LorePack,
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        # target_count=8 with batch_size=5 → up to 2 batches; approximate subtask_total
        target_count = 8
        yield progress_event(
            "events_data", "started",
            stage_index=_STAGE_INDEX["events_data"],
            total_stages=TOTAL_STAGES,
            subtask_total=target_count,
        )
        events_data: list[EventDataEntry] = []
        # Extract location names for events_data_builder
        location_names = [
            loc["name"] if isinstance(loc, dict) else str(loc)
            for loc in locations
            if (loc["name"] if isinstance(loc, dict) else loc)
        ]
        try:
            events_data = await with_transient_retry(
                lambda: build_events_data(
                    description=description,
                    ip_canon=ip_canon,
                    characters=characters,
                    locations=location_names,
                    shared_events=shared_events,
                    lore_pack=lore_pack,
                    llm_router=self.llm,
                    target_count=target_count,
                    batch_size=5,
                    concurrency=3,
                ),
                max_attempts=3,
                on_retry=self._make_retry_logger("events_data"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("events_data_failed", error=str(exc))
            yield _stage_failure_warning(
                "events_data", "events_data_failed", exc,
                "世界事件数据生成失败，世界 0 个事件；玩家进游戏后没有事件触发，建议重跑",
            )
            events_data = []

        self._last_events_data = events_data
        await self._record_intermediate(
            "events_data", [e.model_dump() for e in events_data]
        )

        # Replay subtask events per event entry (batch emit after builder completes)
        def _event_label(ev_obj) -> str:
            summary = getattr(ev_obj, "summary", "") or ""
            # Short label fits inline display (single-line panel row).
            return summary[:12] + "…" if len(summary) > 12 else summary

        for i, ev in enumerate(events_data):
            ev_id = getattr(ev, "id", None) or (ev.model_dump().get("id") if hasattr(ev, "model_dump") else "")
            yield progress_event(
                "events_data", "subtask_completed",
                subtask_key=f"event:{ev_id or i}",
                subtask_index=i + 1,
                subtask_total=target_count,
                payload_summary={
                    "event_id": ev_id or str(i),
                    "title": _event_label(ev),
                },
            )

        clue_count = sum(
            len(getattr(getattr(ev, "effects", None), "spawn_clues", []) or [])
            for ev in events_data
        )
        yield progress_event(
            "events_data", "completed",
            stage_index=_STAGE_INDEX["events_data"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            event_count=len(events_data),
            clue_count=clue_count,
            sample=[_event_label(ev) for ev in events_data[:2] if getattr(ev, "summary", "")],
        )

    # =========================================================================
    # Stage G: playable
    # =========================================================================

    async def _run_playable(
        self,
        characters: list[Character],
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        yield progress_event(
            "playable", "started",
            stage_index=_STAGE_INDEX["playable"],
            total_stages=TOTAL_STAGES,
        )

        # Primary: is_image_target=True (set by roster planner — authoritative)
        playable_chars = [c for c in characters if c.is_image_target]

        # Augment: 始终扩一轮，只针对"高概率可玩"的角色（玩家可能扮演 / 未来
        # 设为 playable 的候选）。不画的：师父 / 派系老大 / 反派 BOSS / 路人
        # —— 他们是 NPC 推动剧情用的，没有"扮演"价值，画了浪费图额度。
        # 宿敌保留：双视角推理剧本里宿敌常作为第二可玩角色。
        # 同时 mutate c.is_image_target=True，让 images 阶段（target_chars 用同一
        # 判断）一致看到这批人。
        PLAYABLE_CANDIDATE_KEYWORDS = ("主角", "宿敌")
        PLAYABLE_CANDIDATE_EXACT = {"主", "女主", "男主", "女主角", "男主角"}
        existing_names = {c.name for c in playable_chars}
        for c in characters:
            if c.name in existing_names:
                continue
            role_tag = (c.role_tag or "").strip()
            if not role_tag:
                continue
            if (
                role_tag in PLAYABLE_CANDIDATE_EXACT
                or any(kw in role_tag for kw in PLAYABLE_CANDIDATE_KEYWORDS)
            ):
                c.is_image_target = True
                playable_chars.append(c)
                existing_names.add(c.name)

        # Last-resort floor: 仍为空时（roster planner + role_tag 双双失灵），按
        # 角色总数的 ~25% 兜底，clamp 到 [3, 8]——保证至少能出几个主要头像，
        # 也不会盲目把所有 NPC 都画了浪费 image quota。
        if not playable_chars and characters:
            floor_n = max(3, min(8, len(characters) // 4))
            for c in characters[:floor_n]:
                c.is_image_target = True
                playable_chars.append(c)
            logger.warning(
                "playable_fallback_forced",
                selected=[c.name for c in playable_chars],
                total_characters=len(characters),
                reason="roster_and_role_tag_both_failed",
            )

        playable_list = [
            {
                "name": c.name,
                "role_tag": c.role_tag,
                "description": c.personality[:100] if c.personality else "",
            }
            for c in playable_chars
        ]
        self._last_playable = playable_list

        yield progress_event(
            "playable", "completed",
            stage_index=_STAGE_INDEX["playable"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            playable_count=len(playable_list),
            names=", ".join(p["name"] for p in playable_list),
            sample=[p["name"] for p in playable_list[:3] if p.get("name")],
        )

    # =========================================================================
    # Stage H: critic (H1 shape + H2 light critic + H3 moderation)
    # =========================================================================

    async def _run_critic(
        self,
        payload: dict,
        lore_pack: LorePack,
        shared_events: list[SharedEvent],
        ip_canon: IPCanon,
        all_warnings: list[str],
        *,
        characters: list | None = None,
        description: str = "",
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        yield progress_event(
            "critic", "started",
            stage_index=_STAGE_INDEX["critic"],
            total_stages=TOTAL_STAGES,
        )

        # H1: shape validation (Python, 0 LLM tokens)
        shape_warnings: list[str] = []
        try:
            shape_warnings = validate_world_shape(payload)
            all_warnings.extend(shape_warnings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("shape_validation_failed", error=str(exc))
            yield _stage_failure_warning(
                "critic", "shape_validation_failed", exc,
                "形状校验失败（纯 Python），quality_warnings 里没有结构问题清单",
            )

        # H2: light critic (concurrent LLM)
        lore_dict = lore_pack.model_dump() if hasattr(lore_pack, "model_dump") else {}
        se_dicts = [
            e.model_dump() if hasattr(e, "model_dump") else e
            for e in shared_events
        ]

        lore_warns: list[str] = []
        se_warns: list[str] = []
        try:
            results = await asyncio.gather(
                with_transient_retry(
                    lambda: light_critic_lore(lore_dict, ip_canon, self.llm),
                    max_attempts=2,
                    on_retry=self._make_retry_logger("critic_lore"),
                ),
                with_transient_retry(
                    lambda: light_critic_shared_events(se_dicts, ip_canon, self.llm),
                    max_attempts=2,
                    on_retry=self._make_retry_logger("critic_shared_events"),
                ),
                return_exceptions=True,
            )
            if isinstance(results[0], list):
                lore_warns = results[0]
            if isinstance(results[1], list):
                se_warns = results[1]
        except Exception as exc:  # noqa: BLE001
            logger.warning("light_critic_failed", error=str(exc))
            yield _stage_failure_warning(
                "critic", "light_critic_failed", exc,
                "轻量质检 LLM 失败，lore + shared_events 的 IP 一致性检查未跑",
            )

        all_warnings.extend(lore_warns)
        all_warnings.extend(se_warns)

        # H2.5: heavy critic (characters + playable)
        if characters is not None:
            canon_dict = ip_canon.model_dump() if hasattr(ip_canon, "model_dump") else {}
            char_dicts = [
                c.model_dump() if hasattr(c, "model_dump") else c
                for c in characters
            ]

            # Anchor metadata for cross-era / IP-fidelity detection
            era_hint = str(payload.get("era") or "")
            genre_hint = str(payload.get("genre") or "")
            ip_pack_ref = getattr(self, "_last_ip_pack", None)
            ip_must_have_names = (
                ip_pack_ref.must_have_character_names() if ip_pack_ref else []
            )

            try:
                updated_chars, char_warns = await with_transient_retry(
                    lambda: heavy_critic_characters(
                        char_dicts, description, canon_dict, self.llm,
                        era=era_hint,
                        genre=genre_hint,
                        ip_must_have=ip_must_have_names,
                    ),
                    max_attempts=2,
                    on_retry=self._make_retry_logger("heavy_critic_characters"),
                )
                all_warnings.extend(char_warns)
                # Replace world_characters in payload with critic-updated version
                payload["world_characters"] = updated_chars
            except Exception as exc:  # noqa: BLE001
                logger.warning("heavy_critic_characters_failed", error=str(exc))
                yield _stage_failure_warning(
                    "critic", "heavy_critic_characters_failed", exc,
                    "深度角色质检失败，角色 personality/secret 一致性未审查，未自动修复",
                )

            try:
                current_chars = payload.get("world_characters") or []
                updated_playable, pl_warns = await with_transient_retry(
                    lambda: heavy_critic_playable(
                        payload.get("playable") or [], current_chars, self.llm
                    ),
                    max_attempts=2,
                    on_retry=self._make_retry_logger("heavy_critic_playable"),
                )
                all_warnings.extend(pl_warns)
                payload["playable"] = updated_playable
            except Exception as exc:  # noqa: BLE001
                logger.warning("heavy_critic_playable_failed", error=str(exc))
                yield _stage_failure_warning(
                    "critic", "heavy_critic_playable_failed", exc,
                    "深度可玩角色质检失败，playable 列表未自动修正",
                )

        # H3: moderation pass
        async def moderation_callable(text: str) -> dict:
            try:
                from engine.moderation import classify
                result = await classify(text)
                return {
                    "flagged": not result.allowed,
                    "reasons": result.flagged_categories,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("moderation_classify_failed", error=str(exc))
                return {"flagged": False, "reasons": []}

        try:
            mod_warns = await moderate_world_payload(payload, moderation_callable)
            all_warnings.extend(mod_warns)
        except Exception as exc:  # noqa: BLE001
            logger.warning("moderation_pass_failed", error=str(exc))
            yield _stage_failure_warning(
                "critic", "moderation_pass_failed", exc,
                "内容审核流程整体失败，本次世界未做内容合规检查",
            )

        yield progress_event(
            "critic", "completed",
            stage_index=_STAGE_INDEX["critic"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            shape_warnings=len(shape_warnings),
            total_warnings=len(all_warnings),
            repair_count=len(all_warnings),
        )

    # =========================================================================
    # Stage I-pre: visual_brief (one LLM call → structured English brief)
    # =========================================================================

    async def _run_visual_brief_stage(
        self,
        *,
        payload: dict,
        characters: list[Character],
    ) -> AsyncIterator[dict]:
        """Derive the per-world ``CoverBrief`` + per-character ``CharacterCoverBrief``
        map via the new cover_brief pipeline.

        Stores results on ``self._cover_brief`` / ``self._char_cover_briefs``
        for the downstream image stage. Briefs are NOT persisted to the
        payload/DB — they're cheap enough to re-derive on each re-generation
        and the old ``visual_brief`` JSONB column was dropped.

        On failure (LLM down / parse error) the helper returns briefs with
        empty english + empty fallback fields; the image builders gracefully
        degrade (drop English subtitle, omit empty descriptors).
        """
        start = time.monotonic()
        yield progress_event(
            "visual_brief", "started",
            stage_index=_STAGE_INDEX["visual_brief"],
            total_stages=TOTAL_STAGES,
        )

        target_chars = [c for c in characters if c.is_image_target]
        char_inputs = [
            {
                "name": c.name,
                "role_tag": getattr(c, "role_tag", ""),
                "personality": getattr(c, "personality", ""),
                "gender": getattr(c, "gender", ""),  # seed value if any
                "is_image_target": True,
            }
            for c in target_chars
        ]

        cover_brief: CoverBrief | None = None
        char_briefs: dict[str, CharacterCoverBrief] = {}
        ok = False
        try:
            async for item in self._run_with_pulse(
                "visual_brief",
                derive_world_cover_brief(
                    world_data=payload,
                    characters=char_inputs,
                    recognition=getattr(self, "_pre_recognition", None),
                    ip_pack=getattr(self, "_last_ip_pack", None),
                    llm=self.llm,
                ),
            ):
                if isinstance(item, tuple) and item[0] == "result":
                    cover_brief, char_briefs = item[1]
                else:
                    yield item
            ok = cover_brief is not None
        except Exception as exc:  # noqa: BLE001
            logger.warning("cover_brief_derivation_failed", error=str(exc))

        self._cover_brief = cover_brief
        self._char_cover_briefs = char_briefs

        yield progress_event(
            "visual_brief", "completed",
            stage_index=_STAGE_INDEX["visual_brief"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            payload_summary={"ok": ok, "characters": len(char_inputs)},
        )

    async def _run_script_visual_brief_stage(
        self,
        *,
        script_payload: dict,
        world_data: dict,
        endings_data: list[dict],
    ) -> AsyncIterator[dict]:
        """Derive the script_title_english + per-ending ``EndingCoverBrief`` map.

        Stores results on ``self._script_title_english`` and
        ``self._ending_cover_briefs`` for the downstream script_images stage.

        The parent world's ``CoverBrief`` is reconstructed from ``world_data``
        (a published or draft World row dict) — this stage runs in script-
        creation flow where the world is already published.
        """
        start = time.monotonic()
        yield progress_event(
            "script_visual_brief", "started",
            stage_index=_SCRIPT_STAGE_INDEX["script_visual_brief"],
            total_stages=_SCRIPT_TOTAL_STAGES,
        )

        # Reconstruct the parent world's CoverBrief from its published row.
        # IP recognition + IP pack are not persisted on World rows for script
        # creation flow, so we degrade gracefully: helper LLM still derives
        # mood + English names from world_name / genre / era alone.
        try:
            world_brief, _ = await derive_world_cover_brief(
                world_data=world_data,
                characters=[],  # script flow doesn't generate portraits
                recognition=None,  # not persisted; degrades to original/hybrid
                ip_pack=None,
                llm=self.llm,
            )
            self._cover_brief = world_brief
        except Exception as exc:  # noqa: BLE001
            logger.warning("script_world_brief_reconstruction_failed", error=str(exc))
            self._cover_brief = None

        script_title_english = ""
        ending_briefs: dict[str, EndingCoverBrief] = {}
        try:
            script_title_english, ending_briefs = await derive_script_cover_helpers(
                script_data=script_payload,
                endings=endings_data,
                llm=self.llm,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("script_cover_helpers_failed", error=str(exc))

        self._script_title_english = script_title_english
        self._ending_cover_briefs = ending_briefs

        yield progress_event(
            "script_visual_brief", "completed",
            stage_index=_SCRIPT_STAGE_INDEX["script_visual_brief"],
            total_stages=_SCRIPT_TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            payload_summary={
                "ok": self._cover_brief is not None,
                "endings": len(ending_briefs),
            },
        )

    # =========================================================================
    # Stage I: images (1 hero @21:9 + N portraits @2:3 + server-cropped 3:2 cover)
    # =========================================================================

    async def _run_images(
        self,
        payload: dict,
        characters: list[Character],
    ) -> AsyncIterator[dict]:
        """Stage I: 真实图片生成（hero 21:9 + is_image_target NPC 2:3 头像 + 服务端裁剪 3:2 cover）。

        并发上限 6（Seedream rate limit，spec §12.3）。单张失败 fallback placeholder。
        """
        start = time.monotonic()
        yield progress_event(
            "images", "started",
            stage_index=_STAGE_INDEX["images"],
            total_stages=TOTAL_STAGES,
        )

        target_chars = [c for c in characters if c.is_image_target]
        world_name = payload.get("name", "world")

        # No image_gen configured (tests / unconfigured) → use placeholder for all
        if not self.image_gen:
            payload["cover_image"] = IMAGE_PLACEHOLDER_URL
            payload["hero_image"] = IMAGE_PLACEHOLDER_URL
            payload["character_images"] = {c.name: IMAGE_PLACEHOLDER_URL for c in target_chars}
            yield progress_event(
                "images", "completed",
                stage_index=_STAGE_INDEX["images"],
                total_stages=TOTAL_STAGES,
                duration_ms=int((time.monotonic() - start) * 1000),
                payload_summary={"npc_avatars": len(target_chars), "skipped": True},
                cover_count=0,
                avatar_count=0,
                image_count=0,
            )
            return

        from services.image_cropper import crop_to_aspect_ratio, materialize_image_bytes

        # Pull pre-computed briefs from visual_brief stage.
        world_brief = getattr(self, "_cover_brief", None)
        char_briefs = getattr(self, "_char_cover_briefs", {})

        if world_brief is None:
            # Brief derivation failed → placeholders everywhere; admin can re-gen.
            payload["cover_image"] = IMAGE_PLACEHOLDER_URL
            payload["hero_image"] = IMAGE_PLACEHOLDER_URL
            payload["character_images"] = {c.name: IMAGE_PLACEHOLDER_URL for c in target_chars}
            yield progress_event(
                "images", "completed",
                stage_index=_STAGE_INDEX["images"],
                total_stages=TOTAL_STAGES,
                duration_ms=int((time.monotonic() - start) * 1000),
                payload_summary={
                    "npc_avatars": len(target_chars), "skipped": True, "reason": "no_brief",
                },
                cover_count=0,
                avatar_count=0,
                image_count=0,
            )
            return

        # Build prompts — 1 hero (21:9) + 1 cover (3:2) + N portraits (2:3).
        # hero and cover are now independent generations (was: hero only, with
        # cover server-cropped from it). Independent cover lets the model
        # compose for small-card thumbnails without 21:9 framing constraints.
        def _world_tiers(builder):
            base = builder(world_brief)
            if world_brief.ip_name and world_brief.ip_name.strip():
                # IP worlds: escalate to 视觉对标 if the direct anchor is blocked.
                return [base, builder(world_brief, ip_fallback=True)]
            return [base]

        hero_task = ("hero", _world_tiers(build_world_hero_prompt), "21:9", "worlds/hero")
        cover_task = ("cover", _world_tiers(build_world_cover_prompt), "3:2", "worlds/cover")
        portrait_tasks = []
        for char in target_chars:
            char_brief = char_briefs.get(char.name)
            if char_brief is None:
                # Helper LLM didn't produce a brief for this character — skip,
                # fallback to placeholder.
                portrait_tasks.append(("npc:" + char.name, [], None, None))
                continue
            prompt = build_character_portrait_prompt(world_brief, char_brief)
            portrait_tasks.append((f"npc:{char.name}", [prompt], "2:3", "characters"))

        image_storage = get_image_storage()
        semaphore = asyncio.Semaphore(6)

        async def gen_image(key, prompt_tiers, aspect_ratio, category):
            if not prompt_tiers:
                return key, IMAGE_PLACEHOLDER_URL, None
            async with semaphore:
                storage_name = world_name if not key.startswith("npc:") else key[4:]
                storage_key = make_image_key(category, storage_name)
                url, result = await _generate_image_with_fallback(
                    self.image_gen, prompt_tiers,
                    aspect_ratio=aspect_ratio, storage=image_storage,
                    storage_key=storage_key, log_key=key,
                )
                # ImageResult returned so the caller can reuse bytes for cropping.
                return key, url, result

        # Run all in parallel.
        all_tasks = [hero_task, cover_task] + portrait_tasks
        total = len(all_tasks)
        yield progress_event(
            "images", "subtask_started",
            subtask_key="batch_kickoff",
            subtask_total=total,
            subtask_index=0,
        )

        # Run image generation under a pulse loop. Without this, gpt-image-2
        # calls (30-90s each, 6 in parallel) leave the SSE stream silent for
        # minutes; the browser / Docker network layer drops the chunked
        # transfer and the client surfaces "网络错误" before the first image
        # comes back. The pulse also gives the user a "still working" signal.
        coros = [gen_image(k, p, ar, cat) for k, p, ar, cat in all_tasks]

        async def _run_all_images() -> list:
            return await asyncio.gather(*coros, return_exceptions=True)

        raw: list = []
        async for item in self._run_with_pulse("images", _run_all_images()):
            if isinstance(item, tuple) and item[0] == "result":
                raw = item[1]  # type: ignore[assignment]
            elif isinstance(item, dict):
                item.setdefault(
                    "message",
                    f"正在生成 {total} 张插画（hero + 列表封面 + 角色头像），请稍候…",
                )
                yield item

        results: dict[str, tuple[str, object | None]] = {}  # key -> (url, ImageResult|None)
        for idx, item in enumerate(raw):
            if isinstance(item, BaseException):
                logger.warning("image_task_exception", index=idx, error=str(item))
                key = all_tasks[idx][0]
                results[key] = (IMAGE_PLACEHOLDER_URL, None)
            else:
                key, url, result = item
                results[key] = (url, result)
            key_str = all_tasks[idx][0]
            label = (
                "Hero 主图" if key_str == "hero"
                else "列表封面" if key_str == "cover"
                else (key_str[4:] + " 头像") if key_str.startswith("npc:")
                else key_str
            )
            yield progress_event(
                "images", "subtask_completed",
                subtask_key=key_str,
                subtask_index=idx + 1,
                subtask_total=total,
                payload_summary={"label": label},
            )

        hero_url, hero_result = results.get("hero", (IMAGE_PLACEHOLDER_URL, None))
        cover_url, _cover_result = results.get("cover", (IMAGE_PLACEHOLDER_URL, None))
        payload["hero_image"] = hero_url

        # Cover fallback chain: cover gen failed → crop from hero; hero also
        # failed → placeholder. Keeps list cards populated even when only one
        # of the two images came through.
        cover_source = "generated"
        if cover_url == IMAGE_PLACEHOLDER_URL and hero_result is not None and hero_url != IMAGE_PLACEHOLDER_URL:
            try:
                hero_bytes = await materialize_image_bytes(hero_result)
                cover_bytes = crop_to_aspect_ratio(hero_bytes, target_w=3, target_h=2)
                cover_key = make_image_key("worlds/cover", world_name, ext="jpg")
                fallback_url = await image_storage.save(cover_bytes, cover_key)
                if fallback_url:
                    cover_url = fallback_url
                    cover_source = "hero_crop_fallback"
            except Exception as exc:  # noqa: BLE001
                logger.warning("cover_crop_fallback_failed", error=str(exc))
        payload["cover_image"] = cover_url

        payload["character_images"] = {
            c.name: results.get(f"npc:{c.name}", (IMAGE_PLACEHOLDER_URL, None))[0]
            for c in target_chars
        }

        placeholder_count = sum(1 for k, (u, _) in results.items() if u == IMAGE_PLACEHOLDER_URL)
        hero_real = 1 if hero_url != IMAGE_PLACEHOLDER_URL else 0
        cover_real = 1 if cover_url != IMAGE_PLACEHOLDER_URL else 0
        avatar_real = sum(
            1 for c in target_chars
            if results.get(f"npc:{c.name}", (IMAGE_PLACEHOLDER_URL, None))[0] != IMAGE_PLACEHOLDER_URL
        )
        yield progress_event(
            "images", "completed",
            stage_index=_STAGE_INDEX["images"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            payload_summary={
                "hero": "real" if hero_real else "placeholder",
                "cover": cover_source if cover_real else "placeholder",
                "npc_avatars": len(target_chars),
                "placeholder_count": placeholder_count,
            },
            cover_count=cover_real,
            avatar_count=avatar_real,
            image_count=hero_real + cover_real + avatar_real,
        )

    # =========================================================================
    # Stage J: validating
    # =========================================================================

    async def _run_validating(
        self,
        payload: dict,
        all_warnings: list[str],
    ) -> AsyncIterator[dict]:
        start = time.monotonic()
        yield progress_event(
            "validating", "started",
            stage_index=_STAGE_INDEX["validating"],
            total_stages=TOTAL_STAGES,
        )
        code = "warnings" if all_warnings else "completed"
        yield progress_event(
            "validating", code,
            stage_index=_STAGE_INDEX["validating"],
            total_stages=TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            warning_count=len(all_warnings),
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _build_working_payload(
        self,
        world_base: dict,
        characters: list[Character],
        playable: list[dict],
        lore_pack: LorePack,
        shared_events: list[SharedEvent],
        events_data: list[EventDataEntry],
        research_pack: ResearchPack,
        relations_pack: RelationsPack,
    ) -> dict:
        """Assemble the full world payload dict (mutable, modified by later stages)."""
        locations = world_base.get("locations", [])
        return {
            # World base fields
            "name": world_base.get("name", ""),
            "description": world_base.get("description", ""),
            "genre": world_base.get("genre", ""),
            "era": world_base.get("era", ""),
            "difficulty": world_base.get("difficulty", "medium"),
            "estimated_time": world_base.get("estimated_time", ""),
            "base_setting": world_base.get("base_setting", ""),
            "free_setting": world_base.get("free_setting", ""),
            "locations": locations,
            # v2 rich content fields
            "research_pack": research_pack.model_dump(),
            "lore_pack": lore_pack.model_dump(),
            "shared_events": [e.model_dump() for e in shared_events],
            "relations_pack": relations_pack.model_dump(),
            "events_data": [e.model_dump() for e in events_data],
            "world_characters": [c.model_dump() for c in characters],
            "playable": playable,
            # Filled by images stage
            "cover_image": PLACEHOLDER_COVER_URL,
            "hero_image": PLACEHOLDER_COVER_URL,
            "character_images": {},
            # Filled by critic + validating
            "quality_warnings": [],
        }

    async def _record_intermediate(self, phase: str, snapshot: dict | list) -> None:
        """Write a checkpoint snapshot; failure is logged but never raised."""
        if not (self.task_service and self.task_id):
            return
        try:
            await self.task_service.record_intermediate(
                self.task_id, phase=phase, snapshot=snapshot
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("record_intermediate_failed", phase=phase, error=str(exc))

    @staticmethod
    def _make_retry_logger(phase: str):
        """Return an on_retry callback that logs a warning (does not yield SSE)."""
        async def _cb(attempt: int, max_attempts: int, exc: BaseException) -> None:
            logger.warning(
                "transient_retry",
                phase=phase,
                attempt=attempt,
                max_attempts=max_attempts,
                error_class=type(exc).__name__,
                error=str(exc),
            )
        return _cb

    async def _run_with_pulse(
        self,
        phase: str,
        work: Coroutine[Any, Any, T],
        *,
        interval: float = 7.0,
    ) -> AsyncIterator[dict | tuple[str, T]]:
        """Run `work` while emitting periodic `pulse` progress events.

        Yields:
            - dict progress events (code == "pulse") every `interval` seconds
            - a final tuple ("result", value) when work succeeds

        Raises whatever exception `work` raises (after cleaning up the tasks).
        """
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        async def runner() -> None:
            try:
                value = await work
            except Exception as exc:  # noqa: BLE001
                await queue.put(("error", exc))
            else:
                await queue.put(("result", value))

        async def pulser() -> None:
            while True:
                await asyncio.sleep(interval)
                await queue.put(("pulse", None))

        work_task = asyncio.create_task(runner())
        pulse_task = asyncio.create_task(pulser())

        try:
            while True:
                kind, payload = await queue.get()
                if kind == "pulse":
                    yield progress_event(phase, "pulse")
                elif kind == "result":
                    yield ("result", payload)
                    return
                elif kind == "error":
                    raise payload  # type: ignore[misc]
        finally:
            pulse_task.cancel()
            if not work_task.done():
                work_task.cancel()
            # Drain cancellation silently.
            for task in (pulse_task, work_task):
                try:
                    await task
                except BaseException:  # noqa: BLE001
                    pass

    # =========================================================================
    # Script v2 — public entry point
    # =========================================================================

    async def create_script(
        self,
        world_data: dict,
        outline: str = "",
    ) -> AsyncIterator[dict]:
        """v2 script 生成 6 阶段流。

        world_data 来自现有 world payload（含 world_characters / locations /
        lore_pack / shared_events / research_pack 等）；outline 是剧本概要描述。
        characters / lore_pack / shared_events 全部继承自 world_data，不重新生成。
        """
        global_start = time.monotonic()
        all_warnings: list[str] = []
        # See create_world for purpose — mirrored here so script-only callers
        # also surface inner-helper failures to the front-end.
        self._stage_errors: dict[str, BaseException] = {}

        # ---- Unpack inherited world data ----
        world_characters: list[dict] = list(world_data.get("world_characters") or [])
        locations: list[dict] = list(world_data.get("locations") or [])
        location_names: list[str] = [
            loc.get("name", "") for loc in locations if loc.get("name")
        ]
        lore_pack_dict: dict = dict(world_data.get("lore_pack") or {})
        shared_events_dicts: list[dict] = list(world_data.get("shared_events") or [])

        # Reconstruct IPCanon from world_data (if present), otherwise empty
        ip_canon_dict: dict = (
            (world_data.get("research_pack") or {}).get("ip_canon") or {}
        )
        ip_canon = IPCanon(
            title_guesses=list(ip_canon_dict.get("title_guesses") or []),
            canonical_names=list(ip_canon_dict.get("canonical_names") or []),
            canonical_places=list(ip_canon_dict.get("canonical_places") or []),
            iconic_objects=list(ip_canon_dict.get("iconic_objects") or []),
            lingo=list(ip_canon_dict.get("lingo") or []),
            notable_events=list(ip_canon_dict.get("notable_events") or []),
        )

        # Inherit parent world's IP knowledge pack so script gen can apply the
        # same strict / loose fidelity constraints as world gen. world_data
        # ip_knowledge_pack is the raw pack_json dict from ip_knowledge_packs.
        from schemas.ip_knowledge_pack import IPKnowledgePack as _IPK
        ip_pack_raw = world_data.get("ip_knowledge_pack")
        ip_pack_obj: _IPK | None = None
        if isinstance(ip_pack_raw, dict) and ip_pack_raw.get("ip_name"):
            try:
                ip_pack_obj = _IPK(**ip_pack_raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("script_v2_ip_pack_parse_failed", error=str(exc))
                ip_pack_obj = None
        # Expose to downstream sub-stages + critic that read off self.
        self._last_ip_pack = ip_pack_obj
        self._fidelity_mode = ip_pack_obj.fidelity_mode if ip_pack_obj else "none"

        # Convert world_characters dicts → Character instances (best-effort)
        characters: list[Character] = []
        for c in world_characters:
            if not isinstance(c, dict):
                continue
            try:
                characters.append(
                    Character(
                        name=c.get("name", ""),
                        personality=c.get("personality", ""),
                        voice_style=c.get("voice_style", ""),
                        role_tag=c.get("role_tag", ""),
                        faction=c.get("faction", ""),
                        is_image_target=bool(
                            c.get("is_image_target") or c.get("playable", False)
                        ),
                        secret=c.get("secret", ""),
                        knowledge=list(c.get("knowledge") or []),
                        schedule=dict(c.get("schedule") or {}),
                        initial_location=c.get("initial_location", ""),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("script_v2_character_parse_skipped", error=str(exc))
                continue

        # LorePack: reconstruct from dict; fall back to empty
        try:
            lore_pack_obj = LorePack(**lore_pack_dict) if lore_pack_dict else LorePack()
        except Exception:  # noqa: BLE001
            lore_pack_obj = LorePack()

        # SharedEvents: reconstruct each entry; skip malformed ones
        shared_events_objs: list[SharedEvent] = []
        for se in shared_events_dicts:
            if not isinstance(se, dict):
                continue
            try:
                shared_events_objs.append(SharedEvent(**se))
            except Exception:  # noqa: BLE001
                continue

        # ==== Stage A: research_pack ====
        yield progress_event(
            "research_pack", "started",
            stage_index=_SCRIPT_STAGE_INDEX["research_pack"],
            total_stages=_SCRIPT_TOTAL_STAGES,
        )
        research_pack: ResearchPack = ResearchPack(summary="", passages=[], ip_canon=ip_canon)
        try:
            research_pack = await with_transient_retry(
                lambda: build_research_pack(
                    description=outline or world_data.get("description", ""),
                    broker=self.broker,
                    llm_router=self.llm,
                    max_passages=settings.research_pack_max_passages,
                    max_passage_chars=settings.research_pack_max_passage_chars,
                ),
                max_attempts=3,
                on_retry=self._make_retry_logger("script_research_pack"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("script_research_pack_failed", error=str(exc))
            yield _stage_failure_warning(
                "research_pack", "script_research_pack_failed", exc,
                "剧本研究素材采集失败，下游事件 / 结局缺少联网素材锚点；建议重跑",
            )
        await self._record_intermediate("script.research_pack", research_pack.model_dump())
        yield progress_event(
            "research_pack", "completed",
            stage_index=_SCRIPT_STAGE_INDEX["research_pack"],
            total_stages=_SCRIPT_TOTAL_STAGES,
            passages=len(research_pack.passages),
        )

        # ==== Stage B: script_base ====
        yield progress_event(
            "script_base", "started",
            stage_index=_SCRIPT_STAGE_INDEX["script_base"],
            total_stages=_SCRIPT_TOTAL_STAGES,
        )
        script_base = await self._generate_script_base_v2(world_data, outline, research_pack)
        if err := self._stage_errors.pop("script_base", None):
            yield _stage_failure_warning(
                "script_base", "script_base_llm_failed", err,
                "剧本基础信息生成失败，已用 outline 兜底（剧本名/简介为占位值），建议重跑",
            )
        await self._record_intermediate("script.script_base", script_base)
        yield progress_event(
            "script_base", "completed",
            stage_index=_SCRIPT_STAGE_INDEX["script_base"],
            total_stages=_SCRIPT_TOTAL_STAGES,
            script_name=script_base.get("name", ""),
        )

        # ==== Stage B.5: roster augmentation (反哺) ====
        # 把本剧本需要、但世界名册里没有的原作 canonical 角色补成「剧本外挂角色」，
        # 加入下游事件/结局可用的工作卡司。世界一律不动；这些角色随剧本走，发布时
        # 落到 Script.local_characters，运行时按 name 与世界角色并集。fail-soft：
        # 补不到就退回「锁世界名册」的旧行为。
        local_characters: list[dict] = []
        if settings.script_roster_augmentation_enabled:
            try:
                from services.script_roster_augmentation import augment_script_roster

                added = await augment_script_roster(
                    world_characters=characters,
                    script_base=script_base,
                    outline=outline,
                    ip_pack=ip_pack_obj,
                    fidelity_mode=self._fidelity_mode,
                    ip_canon=research_pack.ip_canon,
                    research_passages=research_pack.passages,
                    locations=location_names,
                    llm_router=self.llm,
                    max_additions=settings.script_roster_augmentation_max_additions,
                )
            except Exception as exc:  # noqa: BLE001 — never block script gen.
                logger.warning("script_roster_augmentation_failed", error=str(exc))
                added = []
            if added:
                characters = characters + added
                local_characters = [c.model_dump() for c in added]
                all_warnings.append(
                    "[roster_augmented] 本剧本外挂了世界名册外的原作角色（随剧本走，未改世界）："
                    + "、".join(c.name for c in added)
                )

        # ==== Stage C: events ====
        yield progress_event(
            "events", "started",
            stage_index=_SCRIPT_STAGE_INDEX["events"],
            total_stages=_SCRIPT_TOTAL_STAGES,
        )
        events_data: list[EventDataEntry] = []
        try:
            events_data = await with_transient_retry(
                lambda: build_events_data(
                    description=outline or world_data.get("description", ""),
                    ip_canon=research_pack.ip_canon,
                    characters=characters,
                    locations=location_names,
                    shared_events=shared_events_objs,
                    lore_pack=lore_pack_obj,
                    llm_router=self.llm,
                    target_count=8,
                    ip_pack=getattr(self, "_last_ip_pack", None),
                    fidelity_mode=getattr(self, "_fidelity_mode", "none"),
                ),
                max_attempts=3,
                on_retry=self._make_retry_logger("script_events"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("script_events_failed", error=str(exc))
            yield _stage_failure_warning(
                "events", "script_events_failed", exc,
                "剧本事件生成失败，剧本 0 个事件（玩家进剧本后没有事件可触发）；强烈建议重跑",
            )
            events_data = []
        await self._record_intermediate(
            "script.events_data", [e.model_dump() for e in events_data]
        )
        yield progress_event(
            "events", "completed",
            stage_index=_SCRIPT_STAGE_INDEX["events"],
            total_stages=_SCRIPT_TOTAL_STAGES,
            event_count=len(events_data),
        )

        # ==== Stage D: endings ====
        yield progress_event(
            "endings", "started",
            stage_index=_SCRIPT_STAGE_INDEX["endings"],
            total_stages=_SCRIPT_TOTAL_STAGES,
        )
        endings_data = await self._generate_endings_v2(
            world_data, outline, script_base, characters, research_pack
        )
        if err := self._stage_errors.pop("endings", None):
            yield _stage_failure_warning(
                "endings", "endings_generation_failed", err,
                "剧本结局生成失败，结局列表为空，建议重跑",
            )
        await self._record_intermediate("script.endings_data", endings_data)
        yield progress_event(
            "endings", "completed",
            stage_index=_SCRIPT_STAGE_INDEX["endings"],
            total_stages=_SCRIPT_TOTAL_STAGES,
            ending_count=len(endings_data),
        )

        # Fail-fast: endings below publish-schema minimum (validate_script_payload
        # requires ≥ 2). Without this gate the script reaches publish_script_draft
        # then fails with SchemaValidationError — much later, with image gen burned.
        warning = _check_min_content(
            phase="endings",
            count=len(endings_data or []),
            minimum=_MIN_SCRIPT_ENDINGS,
            code="endings_count_below_minimum",
            what="结局数量",
        )
        if warning is not None:
            logger.warning(
                "pipeline_aborted_low_content",
                stage="endings",
                count=len(endings_data or []),
                minimum=2,
            )
            yield warning
            yield error_event(
                message=warning["message"],
                code="pipeline_aborted_low_content",
                phase="endings",
            )
            return

        # ==== Stage E: playable (LLM-curated per-script viewpoints) ====
        yield progress_event(
            "playable", "started",
            stage_index=_SCRIPT_STAGE_INDEX["playable"],
            total_stages=_SCRIPT_TOTAL_STAGES,
        )
        playable = await self._select_script_playable_curated(world_characters, script_base)
        await self._record_intermediate("script.playable", playable)
        yield progress_event(
            "playable", "completed",
            stage_index=_SCRIPT_STAGE_INDEX["playable"],
            total_stages=_SCRIPT_TOTAL_STAGES,
            playable_count=len(playable),
        )

        # ==== Stage F: critic (shape + light LLM critic + moderation) ====
        yield progress_event(
            "critic", "started",
            stage_index=_SCRIPT_STAGE_INDEX["critic"],
            total_stages=_SCRIPT_TOTAL_STAGES,
        )

        # Build minimal payload for validate_world_shape + moderation
        working_payload = {
            "name": script_base.get("name", ""),
            "description": script_base.get("description", ""),
            "script_setting": script_base.get("script_setting", ""),
            "script_type": script_base.get("script_type", "mystery"),
            "events": [e.model_dump() for e in events_data],
            "events_data": [e.model_dump() for e in events_data],
            "endings": endings_data,
            "playable": playable,
            # 含外挂角色，让 shape 校验 + moderation 覆盖到新补的角色文本。
            "world_characters": world_characters + local_characters,
            "locations": locations,
        }

        # H1: shape validation (Python, 0 LLM tokens)
        try:
            shape_warnings = validate_world_shape(working_payload)
            all_warnings.extend(shape_warnings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("script_shape_validation_failed", error=str(exc))
            yield _stage_failure_warning(
                "critic", "script_shape_validation_failed", exc,
                "剧本形状校验失败，quality_warnings 里没有结构问题清单",
            )

        # H2: light critic on events (reuse shared_events critic for IP consistency)
        try:
            events_warns = await with_transient_retry(
                lambda: light_critic_shared_events(
                    [e.model_dump() for e in events_data],
                    research_pack.ip_canon,
                    self.llm,
                ),
                max_attempts=2,
                on_retry=self._make_retry_logger("script_critic_events"),
            )
            all_warnings.extend(events_warns)
        except Exception as exc:  # noqa: BLE001
            logger.warning("script_events_critic_failed", error=str(exc))
            yield _stage_failure_warning(
                "critic", "script_events_critic_failed", exc,
                "剧本事件轻质检 LLM 失败，事件 IP 一致性未检查",
            )

        # H2.5: heavy critic on endings — IP fidelity + era/genre anachronism
        ip_pack_ref = getattr(self, "_last_ip_pack", None)
        fidelity_ref = getattr(self, "_fidelity_mode", "none")
        try:
            ending_warns = await with_transient_retry(
                lambda: heavy_critic_endings(
                    endings_data,
                    script_base.get("script_setting", ""),
                    self.llm,
                    era=str(world_data.get("era", "")),
                    genre=str(world_data.get("genre", "")),
                    ip_must_have=(
                        ip_pack_ref.must_have_character_names() if ip_pack_ref else []
                    ),
                    fidelity_mode=fidelity_ref,
                ),
                max_attempts=2,
                on_retry=self._make_retry_logger("script_critic_endings"),
            )
            all_warnings.extend(ending_warns)
        except Exception as exc:  # noqa: BLE001
            logger.warning("script_endings_critic_failed", error=str(exc))
            yield _stage_failure_warning(
                "critic", "script_endings_critic_failed", exc,
                "剧本结局深度质检失败，结局 IP / 时代一致性未检查",
            )

        # H3: moderation pass
        async def _moderation_callable(text: str) -> dict:
            try:
                from engine.moderation import classify
                result = await classify(text)
                return {"flagged": not result.allowed, "reasons": result.flagged_categories}
            except Exception as exc:  # noqa: BLE001
                logger.warning("script_moderation_classify_failed", error=str(exc))
                return {"flagged": False, "reasons": []}

        try:
            mod_warns = await moderate_world_payload(working_payload, _moderation_callable)
            all_warnings.extend(mod_warns)
        except Exception as exc:  # noqa: BLE001
            logger.warning("script_moderation_failed", error=str(exc))
            yield _stage_failure_warning(
                "critic", "script_moderation_failed", exc,
                "剧本内容审核流程整体失败，本次剧本未做内容合规检查",
            )

        yield progress_event(
            "critic", "completed",
            stage_index=_SCRIPT_STAGE_INDEX["critic"],
            total_stages=_SCRIPT_TOTAL_STAGES,
            total_warnings=len(all_warnings),
        )

        # ==== Stage G: script_visual_brief ====
        async for evt in self._run_script_visual_brief_stage(
            script_payload=working_payload, world_data=world_data, endings_data=endings_data,
        ):
            yield evt

        # ==== Stage H: script_images (script cover 3:2 + N ending cards 3:2) ====
        yield progress_event(
            "script_images", "started",
            stage_index=_SCRIPT_STAGE_INDEX["script_images"],
            total_stages=_SCRIPT_TOTAL_STAGES,
        )

        script_cover_url = IMAGE_PLACEHOLDER_URL
        ending_image_results: dict[str, str] = {}  # ending_title -> url

        world_brief = getattr(self, "_cover_brief", None)
        script_title_english = getattr(self, "_script_title_english", "")
        ending_briefs = getattr(self, "_ending_cover_briefs", {})

        if not (self.image_gen and world_brief):
            reason = "no_image_gen" if not self.image_gen else "no_world_brief"
            logger.info("script_image_skipped", reason=reason)
        else:
            # Script cover
            try:
                script_kwargs = dict(
                    script_title=script_base.get("name", ""),
                    script_title_english=script_title_english,
                    script_essence=(script_base.get("description") or ""),
                )
                script_tiers = [build_script_cover_prompt(world_brief, **script_kwargs)]
                if world_brief.ip_name and world_brief.ip_name.strip():
                    script_tiers.append(
                        build_script_cover_prompt(world_brief, ip_fallback=True, **script_kwargs)
                    )
                storage = get_image_storage()
                storage_key = make_image_key("scripts/cover", script_base.get("name", "script"))
                script_cover_url, _ = await _generate_image_with_fallback(
                    self.image_gen, script_tiers,
                    aspect_ratio="3:2", storage=storage,
                    storage_key=storage_key, log_key="script_cover",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("script_cover_failed", error=str(exc))

            # Ending cards — one per ending. Failures leave the URL NULL so
            # the front-end falls back to text-only ending display (Q6 decision).
            for ending_title, ending_brief in ending_briefs.items():
                try:
                    prompt = build_ending_card_prompt(world_brief, ending_brief)
                    result = await self.image_gen.generate_image(prompt, aspect_ratio="3:2")
                    storage = get_image_storage()
                    storage_key = make_image_key(
                        "endings", f"{script_base.get('name', 'script')}_{ending_title}"
                    )
                    saved = await save_generated_image_result(storage, result, storage_key)
                    if saved and saved != IMAGE_PLACEHOLDER_URL:
                        ending_image_results[ending_title] = saved
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "ending_card_failed", ending=ending_title, error=str(exc),
                    )

        # Stamp ending_image URL onto each ending in endings_data so the
        # publish_service can pick it up when creating Ending rows.
        for ending in endings_data:
            url = ending_image_results.get(ending.get("title", ""))
            if url:
                ending["cover_image"] = url

        yield progress_event(
            "script_images", "completed",
            stage_index=_SCRIPT_STAGE_INDEX["script_images"],
            total_stages=_SCRIPT_TOTAL_STAGES,
            payload_summary={
                "cover": "real" if script_cover_url != IMAGE_PLACEHOLDER_URL else "placeholder",
                "ending_cards": len(ending_image_results),
                "ending_cards_total": len(ending_briefs),
            },
        )

        # 把选出的可玩角色解析成 WorldCharacter UUID（落库口径）。只认世界里仍
        # playable 的角色，保证「剧本可玩 ⊆ 世界可玩」且不会把 NPC/不存在的人选进来。
        # world_characters 由 generation_task_service 注入了 id。空名单 = 运行时放行全部。
        playable_id_by_name = {
            c.get("name"): str(c.get("id"))
            for c in world_characters
            if isinstance(c, dict) and c.get("playable") and c.get("id")
        }
        playable_character_ids: list[str] = []
        for item in playable:
            cid = playable_id_by_name.get(item.get("name")) if isinstance(item, dict) else None
            if cid and cid not in playable_character_ids:
                playable_character_ids.append(cid)

        # ==== Final result + done ====
        final_payload: dict = {
            "name": script_base.get("name", ""),
            "description": script_base.get("description", ""),
            "difficulty": script_base.get("difficulty", 3),
            "estimated_time": script_base.get("estimated_time", "30-60 min"),
            "script_setting": script_base.get("script_setting", ""),
            "script_type": script_base.get("script_type", "mystery"),
            "events": [e.model_dump() for e in events_data],
            "events_data": [e.model_dump() for e in events_data],
            "clues": {},
            "endings": endings_data,
            "playable": playable,
            "playable_character_ids": playable_character_ids,
            # 剧本外挂角色（反哺产物）：随剧本走，发布时落 Script.local_characters，
            # 运行时与世界角色并集。世界不被改动。
            "local_characters": local_characters,
            "research_pack": research_pack.model_dump(),
            "cover_image": script_cover_url,
            "quality_warnings": all_warnings,
        }
        yield result_event(final_payload)
        yield done_event()

        logger.info(
            "world_creator_v2_create_script_done",
            duration_s=round(time.monotonic() - global_start, 2),
            event_count=len(events_data),
            ending_count=len(endings_data),
        )

    # =========================================================================
    # Script v2 — stage helpers
    # =========================================================================

    async def _generate_script_base_v2(
        self,
        world_data: dict,
        outline: str,
        research_pack: ResearchPack,
    ) -> dict:
        """Single LLM call to produce script name / description / setting / type.

        Falls back to safe defaults on any failure (never raises).
        """
        from services.script_premise_recommender import BANNED_TITLE_WORDS

        system = (
            "你是剧本作家。基于世界设定和剧情大纲，生成剧本基础信息。\n"
            "输出严格 JSON，格式：\n"
            '{\n'
            '  "name": "剧本名",\n'
            '  "description": "剧本简介（1-2 句）",\n'
            '  "script_setting": "剧本设定（剧情背景，绝不向玩家展示）",\n'
            '  "script_type": "mystery|adventure|drama|action",\n'
            '  "difficulty": 3,\n'
            '  "estimated_time": "30-60 min"\n'
            "}\n"
            "命名要求（name）：贴原作语汇、用世界里真实的地名 / 事件名 / 专有名词；"
            f"禁止使用这些通用煽情套词：{'、'.join(BANNED_TITLE_WORDS)}；"
            "不要堆砌「四字地名＋抽象词」的 AI 腔标题。\n"
            "若提供了 existing_scripts（同世界已有剧本），本剧本的核心真相 / 主线 / "
            "切入阶段必须与之错开，不要重复已做过的内容。\n"
            "严格 JSON 输出，不含任何解释文字。"
        )

        # Inject IP fidelity constraint when strict / loose
        ip_pack = getattr(self, "_last_ip_pack", None)
        fidelity = getattr(self, "_fidelity_mode", "none")
        ip_fidelity_block: dict = {}
        if ip_pack and fidelity in ("strict", "loose"):
            ip_fidelity_block = {
                "ip_name": ip_pack.ip_name,
                "fidelity_mode": fidelity,
                "must_have_characters": ip_pack.must_have_character_names(),
                "must_have_places": ip_pack.must_have_place_names(),
                "ip_summary": (ip_pack.summary or "")[:600],
                "instruction": (
                    "剧本必须忠于上述原作锚点：核心冲突、主线 / 派系、关键人物动机均不得偏离。"
                    if fidelity == "strict"
                    else "剧本应以上述原作为参考，允许小幅扩展但保持气质一致。"
                ),
            }

        ip_canon_dump = research_pack.ip_canon.model_dump()
        existing_scripts_brief = [
            {
                "name": s.get("name", ""),
                "description": (s.get("description", "") or "")[:120],
            }
            for s in (world_data.get("existing_scripts") or [])[:8]
            if isinstance(s, dict)
        ]
        user_content = json.dumps(
            {
                "world_name": world_data.get("name", ""),
                "world_setting": (world_data.get("base_setting", "") or "")[:800],
                "world_era": world_data.get("era", ""),
                "world_genre": world_data.get("genre", ""),
                "outline": outline,
                "ip_canon": ip_canon_dump,
                "ip_fidelity": ip_fidelity_block,
                "existing_scripts": existing_scripts_brief,
            },
            ensure_ascii=False,
        )
        try:
            text = await with_transient_retry(
                lambda: _collect_stream_text(
                    self.llm,
                    system=system,
                    messages=[{"role": "user", "content": user_content}],
                    max_tokens=2048,
                ),
                max_attempts=3,
                on_retry=self._make_retry_logger("script_base"),
            )
            data = _extract_json_from_text(text) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("script_base_v2_llm_failed", error=str(exc))
            self._stage_errors["script_base"] = exc
            data = {}

        return {
            "name": str(data.get("name") or outline[:30] or "未命名剧本"),
            "description": str(data.get("description") or outline or ""),
            "script_setting": str(data.get("script_setting") or ""),
            "script_type": str(data.get("script_type") or "mystery"),
            "difficulty": int(data.get("difficulty") or 3),
            "estimated_time": str(data.get("estimated_time") or "30-60 min"),
        }

    async def _generate_endings_v2(
        self,
        world_data: dict,
        outline: str,
        script_base: dict,
        characters: list[Character],
        research_pack: ResearchPack,
    ) -> list[dict]:
        """Produce 3-5 endings with full runtime-compatible shape.

        Required fields per ending: ending_type / title / description /
        soft_conditions / priority. quality is preserved for legacy UI but
        derived alongside ending_type. Retries up to 3 times, injecting the
        previous attempt's validation errors as feedback on each retry.

        Returns [] only when no valid endings could be produced.
        """
        system = (
            "你是剧本结局设计师。给剧本设计 3-5 个不同的结局，覆盖好/中/坏多种走向。\n"
            "输出严格 JSON（不含 markdown 代码块），结构：\n"
            '{\n'
            '  "endings": [\n'
            '    {\n'
            '      "ending_type": "good | normal | bad | hidden | timeout",\n'
            '      "title": "结局标题（玩家可见，6-20 字）",\n'
            '      "description": "结局完整描述（玩家可见，>=80 字）",\n'
            '      "soft_conditions": "用自然语言描述判定条件，供运行时 AI 主持人比对玩家走向",\n'
            '      "priority": 整数（数值越大越优先匹配，建议 0-10）,\n'
            '      "quality": "best | good | neutral | bad | worst"\n'
            '    }\n'
            '  ]\n'
            "}\n"
            "硬约束：\n"
            "- ending_type 必须从枚举里选；不要发明新类型。\n"
            "- soft_conditions 用一句话写明判定依据，能让 AI 主持人判断玩家是否走向此结局。\n"
            "- 不要遗漏任何字段；缺字段会导致运行时报错。\n"
            "- 至少 3 个、至多 5 个不同的结局。"
        )
        char_names = [c.name for c in characters[:10]]

        # IP fidelity for endings: nudge canonical endings if strict
        ip_pack = getattr(self, "_last_ip_pack", None)
        fidelity = getattr(self, "_fidelity_mode", "none")
        ip_fidelity_block: dict = {}
        if ip_pack and fidelity in ("strict", "loose"):
            # BUGS #23: 把"不可改写"的原作关系/反派身份显式列出来，避免
            # ending 编排把玛丽设为莫里亚蒂私生女这种 plot 层颠覆。
            canonical_relations = [
                {
                    "name": c.name,
                    "role": c.role_in_story,
                    "relation": c.relation_to_protagonist,
                }
                for c in ip_pack.characters
                if c.must_have and (c.role_in_story or c.relation_to_protagonist)
            ]
            canonical_arcs = [
                {"when": t.when, "event": t.event}
                for t in (ip_pack.timeline or [])
                if t.event
            ][:8]
            ip_fidelity_block = {
                "ip_name": ip_pack.ip_name,
                "fidelity_mode": fidelity,
                "must_have_characters": ip_pack.must_have_character_names(),
                "canonical_relations_immutable": canonical_relations,
                "canonical_arcs_reference": canonical_arcs,
                "canonical_endings_hint": (
                    "结局应当包含至少一个贴近原作真实结局的路径（标 quality=best 或 good）。"
                    if fidelity == "strict"
                    else "结局可参考原作走向，但允许玩家用反叙事走出新分支。"
                ),
                "plot_level_constraints": [
                    "canonical_relations_immutable 列出的角色关系/身份不可颠覆——"
                    "原作明确为对手的两人不能在结局里被改写成亲属或盟友；"
                    "原作明确的反派身份不能转嫁给其他角色。",
                    "新结局可以走出原作没写过的分支，但不能把原作主线 NPC "
                    "的核心身份/阵营/血缘关系反转（典型反例：将『敌对方』改写为『私生子/女』）。",
                    "如果某个结局需要颠覆原作关系，请改成『把这个角色替换成原创 NPC』而不是改写原 IP 人物。",
                ],
            }

        user_content = json.dumps(
            {
                "script_name": script_base.get("name", ""),
                "script_setting": (script_base.get("script_setting", "") or "")[:600],
                "world_era": world_data.get("era", ""),
                "world_genre": world_data.get("genre", ""),
                "outline": outline,
                "characters": char_names,
                "ip_canon": research_pack.ip_canon.model_dump(),
                "ip_fidelity": ip_fidelity_block,
            },
            ensure_ascii=False,
        )

        last_issues: list[str] = []
        for attempt in range(3):
            mutated_system = system
            if last_issues:
                mutated_system = (
                    system
                    + "\n\n## 上次输出的问题\n"
                    + "\n".join(f"- {i}" for i in last_issues[:10])
                    + "\n请这次输出严格满足 schema，特别注意上面列出的字段。"
                )
            try:
                text = await _collect_stream_text(
                    self.llm,
                    system=mutated_system,
                    messages=[{"role": "user", "content": user_content}],
                    max_tokens=4096,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "script_endings_v2_call_failed",
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt == 2:
                    self._stage_errors["endings"] = exc
                    return []
                continue

            data = _extract_json_from_text(text) or {}
            raw_endings = data.get("endings") or []
            result: list[dict] = []
            current_issues: list[str] = []
            for idx, e in enumerate(raw_endings):
                if not isinstance(e, dict):
                    current_issues.append(f"endings[{idx}] is not a dict")
                    continue
                normalized = {
                    "ending_type": str(e.get("ending_type") or "").strip(),
                    "title": str(e.get("title") or e.get("name") or "").strip(),
                    "description": str(e.get("description") or "").strip(),
                    "soft_conditions": str(e.get("soft_conditions") or e.get("condition") or "").strip(),
                    "priority": int(e["priority"]) if isinstance(e.get("priority"), (int, float)) else 0,
                    "quality": str(e.get("quality") or "neutral").strip(),
                    # Keep `name` mirror for legacy admin UI that still reads it.
                    "name": str(e.get("title") or e.get("name") or "").strip(),
                }
                issues = _validate_ending_payload(normalized)
                if issues:
                    current_issues.extend(f"endings[{idx}]: {i}" for i in issues)
                    continue
                result.append(normalized)

            if result and not current_issues:
                return result
            if len(result) >= 3:
                # Partial success: enough valid endings to ship; log the bad ones.
                logger.warning(
                    "script_endings_v2_partial",
                    valid=len(result),
                    dropped_issues=current_issues[:5],
                )
                return result
            last_issues = current_issues or ["no endings produced"]
            logger.warning(
                "script_endings_v2_retry",
                attempt=attempt,
                issues=last_issues[:5],
            )

        self._stage_errors["endings"] = ValueError(
            f"endings generation failed after 3 attempts: {last_issues}"
        )
        return []

    def _select_script_playable_v2(self, world_characters: list[dict]) -> list[dict]:
        """Select playable characters from world_data without LLM.

        Priority: is_image_target=True OR playable=True OR role_tag contains "主角".
        Falls back to first 3 characters if none qualify.
        """
        selected: list[dict] = []
        for c in world_characters:
            if not isinstance(c, dict):
                continue
            is_target = c.get("is_image_target") or c.get("playable", False)
            role = str(c.get("role_tag", ""))
            if is_target or "主角" in role or role == "主":
                selected.append(
                    {
                        "name": c.get("name", ""),
                        "role_tag": c.get("role_tag", ""),
                        "personality": (c.get("personality", "") or "")[:80],
                    }
                )
        if not selected:
            # Fallback: first 3 characters
            for c in world_characters[:3]:
                if not isinstance(c, dict):
                    continue
                selected.append(
                    {
                        "name": c.get("name", ""),
                        "role_tag": c.get("role_tag", ""),
                        "personality": (c.get("personality", "") or "")[:80],
                    }
                )
        return selected

    async def _select_script_playable_curated(
        self, world_characters: list[dict], script_base: dict
    ) -> list[dict]:
        """LLM-curate the per-script playable viewpoints from the world-playable
        roster, so a script opens ~3-4 story-relevant POVs instead of every
        playable world character. Reuses the v1 build_playable_prompt + playable
        brief. Falls back to _select_script_playable_v2 (all world-playable) on
        any LLM failure or unusable output — playable selection must never break
        script generation, and "剧本可玩 ⊆ 世界可玩" is preserved by only ever
        choosing from world-playable candidates.
        """
        # Lazy imports avoid any import cycle with the prompt builder / strategy schemas.
        from schemas.generation_strategy import normalize_playable_brief
        from services.generation_prompt_builder import GenerationPromptBuilder

        candidates = [
            c
            for c in world_characters
            if isinstance(c, dict)
            and (c.get("playable") or c.get("is_image_target"))
            and c.get("name")
        ]
        brief = normalize_playable_brief(None)
        # Too few to meaningfully curate — keep the whole (small) roster.
        if len(candidates) <= 3:
            return self._select_script_playable_v2(world_characters)

        prompt = GenerationPromptBuilder().build_playable_prompt(
            title=str(script_base.get("name") or ""),
            summary=str(script_base.get("description") or "")[:600],
            characters=[
                {"name": c.get("name", ""), "personality": c.get("personality", "")}
                for c in candidates
            ],
            playable_brief=brief,
            script_mode=True,
        )
        prompt += (
            '\n\n只返回 JSON，格式：{"playable_characters":[{"name":"..."}]}；'
            "name 必须与上面人物列表中的名字完全一致，不要创造列表外的新名字。"
        )
        try:
            text = await with_transient_retry(
                lambda: _collect_stream_text(
                    self.llm,
                    system="你是资深剧本设计师，按本剧本的剧情挑选最值得开放给玩家的可玩视角。只返回 JSON。",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024,
                ),
                max_attempts=3,
                on_retry=self._make_retry_logger("playable"),
            )
            data = _extract_json_from_text(text) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("playable_curated_llm_failed", error=str(exc))
            data = {}

        by_name = {c.get("name"): c for c in candidates}
        selected: list[dict] = []
        seen: set[str] = set()
        for item in data.get("playable_characters") or []:
            name = (
                item.get("name")
                if isinstance(item, dict)
                else (item if isinstance(item, str) else None)
            )
            c = by_name.get(str(name)) if name else None
            if c and c["name"] not in seen:
                seen.add(c["name"])
                selected.append(
                    {
                        "name": c.get("name", ""),
                        "role_tag": c.get("role_tag", ""),
                        "personality": (c.get("personality", "") or "")[:80],
                    }
                )
        selected = selected[: max(brief.playable_count_target, brief.recommended_count_target)]
        # LLM gave nothing usable → keep the safe "all world-playable" behavior.
        if not selected:
            return self._select_script_playable_v2(world_characters)
        return selected
