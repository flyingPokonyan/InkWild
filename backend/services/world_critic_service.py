"""World critic 分级（spec §5）：
- validate_world_shape: 形状 + 引用一致性，无 LLM
- light_critic_lore / light_critic_shared_events: 单 LLM pass 写 quality_warnings 不修复
- heavy_critic_characters: 重 critic，含 review + repair pass（v1 同质量）
- heavy_critic_playable: playable review，只检不修
"""
from __future__ import annotations

import asyncio
import json
import re
import structlog

from schemas.research_pack import IPCanon
from services.research_pack_builder import _collect_stream_text, _extract_json_from_text

logger = structlog.get_logger()

# ---- 形状校验 ----

def validate_world_shape(payload: dict) -> list[str]:
    """对 world payload 做形状 + 引用一致性校验，返回 warning string list。

    检查规则（spec §4.4）：
    - playable[].name ⊆ world_characters[].name
    - world_characters[].schedule.values() ⊆ locations[].name
    - world_characters[].initial_location ⊆ locations[].name
    - shared_events[].involved_npcs ⊆ world_characters[].name
    - events_data[].kind == 'npc_intent_driven' 时 trigger.npc_name ⊆ world_characters[].name
    - events_data[].rumors[].knower_npcs ⊆ world_characters[].name
    - events_data[].effects.npc_mood_changes keys ⊆ world_characters[].name

    已 disabled=true 的 event 不再校验引用（避免重复 warn）。
    """
    warnings: list[str] = []

    chars = payload.get("world_characters") or []
    char_names: set[str] = {c.get("name") for c in chars if c.get("name")}
    locations = payload.get("locations") or []
    location_names: set[str] = {loc.get("name") for loc in locations if loc.get("name")}

    # playable ⊆ characters
    playable = payload.get("playable") or []
    for p in playable:
        name = p.get("name")
        if name not in char_names:
            warnings.append(f"shape_violation: playable_unknown_npc: {name}")

    # schedule.values() ⊆ locations  +  initial_location ⊆ locations
    for c in chars:
        char_name = c.get("name", "?")
        schedule = c.get("schedule") or {}
        for slot, loc in schedule.items():
            if loc and loc not in location_names:
                warnings.append(
                    f"shape_violation: schedule_unknown_location: {char_name}.schedule[{slot}]={loc}"
                )
        init_loc = c.get("initial_location")
        if init_loc and init_loc not in location_names:
            warnings.append(
                f"shape_violation: initial_location_unknown: {char_name}={init_loc}"
            )

    # shared_events.involved_npcs ⊆ characters
    for ev in (payload.get("shared_events") or []):
        ev_id = ev.get("id", "?")
        for npc in (ev.get("involved_npcs") or []):
            if npc not in char_names:
                warnings.append(f"shape_violation: shared_event_unknown_npc: {ev_id}={npc}")

    # events_data 引用（disabled 的跳过）
    for ev in (payload.get("events_data") or []):
        if ev.get("disabled"):
            continue
        ev_id = ev.get("id", "?")
        kind = ev.get("kind")
        trigger = ev.get("trigger") or {}

        # npc_intent_driven: trigger.npc_name ⊆ characters
        if kind == "npc_intent_driven":
            npc_name = trigger.get("npc_name")
            if npc_name and npc_name not in char_names:
                warnings.append(
                    f"shape_violation: event_intent_unknown_npc: {ev_id}={npc_name}"
                )

        # rumors[].knower_npcs ⊆ characters
        for r in (ev.get("rumors") or []):
            for kn in (r.get("knower_npcs") or []):
                if kn not in char_names:
                    warnings.append(
                        f"shape_violation: rumor_knower_unknown: {ev_id}={kn}"
                    )

        # effects.npc_mood_changes keys ⊆ characters
        mood = (ev.get("effects") or {}).get("npc_mood_changes") or {}
        for k in mood.keys():
            if k not in char_names:
                warnings.append(
                    f"shape_violation: mood_change_unknown_npc: {ev_id}={k}"
                )

    return warnings


# ---- 轻 critic ----

_LORE_CRITIC_SYSTEM = """你是世界设定 critic。审查 lore_pack 是否：
- 内部矛盾（同维度的 content_blocks 互相打架）
- 与 ip_canon 冲突（如复刻某 IP 但 lore 跟原作不符）
- 维度间冲突
输出严格 JSON {"warnings": ["问题描述", ...]}，无问题输出 {"warnings": []}。"""

_SHARED_EVENTS_CRITIC_SYSTEM = """你是事件 critic。审查 shared_events 是否：
- 与 ip_canon 矛盾（人名 / 事件冲突）
- 事件之间相互矛盾（时间线 / 涉及 NPC 矛盾）
输出严格 JSON {"warnings": ["问题描述", ...]}，无问题输出 {"warnings": []}。"""


async def light_critic_lore(lore_pack: dict, ip_canon: IPCanon, llm_router) -> list[str]:
    """对 lore_pack 跑单次 LLM critic pass，返回 warnings。失败/空 pack 返回 []。"""
    if not lore_pack or not (lore_pack.get("dimensions") or []):
        return []
    try:
        canon_data = (
            ip_canon.model_dump()
            if hasattr(ip_canon, "model_dump")
            else ip_canon.dict()
        )
        user_content = json.dumps(
            {"lore_pack": lore_pack, "ip_canon": canon_data},
            ensure_ascii=False,
        )
        text = await _collect_stream_text(
            llm_router,
            system=_LORE_CRITIC_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=2048,
        )
        data = _extract_json_from_text(text)
        if not data:
            return []
        warnings = data.get("warnings") or []
        return [str(w) for w in warnings if w]
    except Exception as exc:  # noqa: BLE001
        logger.warning("light_critic_lore_failed", error=str(exc))
        return []


async def light_critic_shared_events(
    shared_events: list[dict], ip_canon: IPCanon, llm_router
) -> list[str]:
    """对 shared_events 跑单次 LLM critic pass，返回 warnings。失败/空列表返回 []。"""
    if not shared_events:
        return []
    try:
        canon_data = (
            ip_canon.model_dump()
            if hasattr(ip_canon, "model_dump")
            else ip_canon.dict()
        )
        user_content = json.dumps(
            {"shared_events": shared_events, "ip_canon": canon_data},
            ensure_ascii=False,
        )
        text = await _collect_stream_text(
            llm_router,
            system=_SHARED_EVENTS_CRITIC_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=2048,
        )
        data = _extract_json_from_text(text)
        if not data:
            return []
        warnings = data.get("warnings") or []
        return [str(w) for w in warnings if w]
    except Exception as exc:  # noqa: BLE001
        logger.warning("light_critic_shared_events_failed", error=str(exc))
        return []


# ---- 重 critic ----

_HEAVY_CRITIC_CHARACTERS_SYSTEM = """你是互动叙事世界的角色质量 critic。
仔细审查给定的 characters 列表，结合 ip_canon / ip_must_have / era 判断是否存在以下问题：
- personality_secret_conflict：personality 与 secret 明显矛盾
- knowledge_inconsistent：knowledge 描述与世界观 / ip_canon 不符
- ip_canon_violation：人物设定违背原著 ip_canon
- ip_must_have_missing：原作必备角色（ip_must_have 列出的）在 characters 中缺失
- ip_non_canon_extra：strict 模式下，characters 中出现了 ip_canon / ip_must_have 都没有的角色，且看起来不是合理的"原创配角"（如混入了其他作品的角色、风格不搭的角色）
- era_anachronism：角色姓名 / 称谓 / 派系背景跟 era 明显错位（例：嘉靖朝出现"叶赫那拉"这种清朝满洲八旗姓氏；明朝出现"道长 / 仙人 / XX洞 主"这种纯玄幻角色；近代历史剧出现武侠风格角色）
- genre_mismatch：角色定位违背 genre（历史正剧混入武侠 / 玄幻 / 异能角色）
- internal_inconsistency：人物内部字段冲突

输出严格 JSON：
{"verdict": "ok|needs_repair", "issues": [{"target": "角色name", "kind": "问题类型", "detail": "具体描述"}]}

无问题时输出：{"verdict": "ok", "issues": []}
只输出 JSON，不含任何解释文字。"""

_HEAVY_REPAIR_CHARACTERS_SYSTEM = """你是互动叙事世界的角色修复专家。
根据 critic 指出的问题，对有问题的角色进行修复。

重要约束：
- **绝不修改 name 字段**（name 是下游引用锚点，改名会破坏 events/rumors/schedule 等引用）
- 只修改有问题的字段（personality / secret / knowledge / schedule / initial_location 等）
- 未提及的角色保持原样，直接包含在输出中
- 修复后只输出有问题的角色（下游会按 name 匹配替换）

输出严格 JSON，格式：
{"characters": [{"name": "...", "personality": "...", "secret": "...", "knowledge": [...], ...（其余字段）}]}

只输出 JSON，不含任何解释文字。"""

_HEAVY_CRITIC_PLAYABLE_SYSTEM = """你是互动叙事世界的可玩角色 critic。
审查 playable 列表中的每个角色是否：
- 存在于 characters 列表中（name 必须能对应）
- role_tag 是否合理（主角 / 玩家视角等，而非反派或群演）

输出严格 JSON，格式：
{"warnings": ["问题描述", ...]}

无问题时输出：{"warnings": []}
只输出 JSON，不含任何解释文字。"""


async def heavy_critic_characters(
    characters: list[dict],
    description: str,
    ip_canon: dict | IPCanon,
    llm_router,
    *,
    allow_repair: bool = True,
    era: str = "",
    genre: str = "",
    ip_must_have: list[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """对 characters 跑一次 review LLM；如发现问题且 allow_repair=True，再调一次 LLM 修复。

    返回：(updated_characters, quality_warnings)

    流程：
    1. critic LLM 收 characters + ip_canon，输出 verdict + issues
    2. 如 verdict=needs_repair 且 allow_repair=True：构造 repair_note → 调主 LLM
       重新出有问题的 characters subset → 用 name 匹配替换原 characters
    3. 修复后再 critic 一次（最多 1 次循环）；仍有 issues 标 quality_warnings

    失败 fallback：直接返回 (characters, []) — 不阻断生成
    name 保护：repair LLM 若改了 name，只接受能匹配到原名的条目。
    """
    if not characters:
        return characters, []

    canon_dict: dict
    if hasattr(ip_canon, "model_dump"):
        canon_dict = ip_canon.model_dump()  # type: ignore[union-attr]
    elif isinstance(ip_canon, dict):
        canon_dict = ip_canon
    else:
        canon_dict = {}

    # ---- Pass 1: critic ----
    try:
        critic_input = json.dumps(
            {
                "characters": characters,
                "ip_canon": canon_dict,
                "ip_must_have": list(ip_must_have or []),
                "era": era,
                "genre": genre,
                "world_description": description,
            },
            ensure_ascii=False,
        )
        critic_text = await _collect_stream_text(
            llm_router,
            system=_HEAVY_CRITIC_CHARACTERS_SYSTEM,
            messages=[{"role": "user", "content": critic_input}],
            max_tokens=2048,
        )
        critic_data = _extract_json_from_text(critic_text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("heavy_critic_characters_pass1_failed", error=str(exc))
        return characters, []

    if not critic_data or not isinstance(critic_data, dict):
        return characters, []

    verdict: str = str(critic_data.get("verdict", "ok"))
    issues: list[dict] = [
        i for i in (critic_data.get("issues") or []) if isinstance(i, dict)
    ]

    if verdict != "needs_repair" or not issues or not allow_repair:
        # Either clean, or allow_repair disabled — collect warnings if any
        if not allow_repair and issues:
            warnings = [
                f"heavy_critic: target={i.get('target','')} kind={i.get('kind','')} detail={i.get('detail','')}"
                for i in issues
            ]
            return characters, warnings
        return characters, []

    # ---- Pass 2: repair ----
    problematic_names = {i.get("target", "") for i in issues if i.get("target")}
    problem_chars = [c for c in characters if c.get("name") in problematic_names]
    issue_details = "; ".join(
        f"[{i.get('target','')}] {i.get('kind','')} — {i.get('detail','')}"
        for i in issues
    )

    try:
        repair_input = json.dumps(
            {
                "characters_to_fix": problem_chars,
                "all_characters": characters,
                "issues": issue_details,
                "ip_canon": canon_dict,
                "ip_must_have": list(ip_must_have or []),
                "era": era,
                "genre": genre,
                "world_description": description,
                "instruction": (
                    "请修复有问题的角色。绝不修改 name 字段，只改 personality / secret / "
                    "knowledge / schedule / initial_location 等内容字段。"
                ),
            },
            ensure_ascii=False,
        )
        repair_text = await _collect_stream_text(
            llm_router,
            system=_HEAVY_REPAIR_CHARACTERS_SYSTEM,
            messages=[{"role": "user", "content": repair_input}],
            max_tokens=3000,
        )
        repair_data = _extract_json_from_text(repair_text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("heavy_critic_characters_repair_failed", error=str(exc))
        return characters, []

    if not repair_data or not isinstance(repair_data, dict):
        return characters, []

    repaired_chars: list[dict] = [
        c for c in (repair_data.get("characters") or [])
        if isinstance(c, dict) and c.get("name")
    ]

    # Merge: only accept repaired chars whose name matches an original char (name protection)
    repaired_name_map = {c["name"]: c for c in repaired_chars if c.get("name")}

    # Repair LLM only edits content fields (personality / secret / knowledge /
    # schedule / initial_location / relations — per the instruction above).
    # Structural fields (role_tag / faction / is_image_target) come from the
    # roster planner; if repaired_name_map[name] is missing them, we must NOT
    # silently zero them out by full-replacing. Bug seen: characters lost
    # role_tag and is_image_target after critic, breaking playable selection
    # and avatar generation downstream.
    REPAIRABLE_FIELDS = {
        "personality",
        "secret",
        "knowledge",
        "schedule",
        "initial_location",
        "initial_peer_relations",
    }
    updated_characters = []
    for orig in characters:
        orig_name = orig.get("name", "")
        if orig_name in repaired_name_map:
            merged = dict(orig)  # start from full original, preserve all fields
            repaired = repaired_name_map[orig_name]
            for fld in REPAIRABLE_FIELDS:
                if fld in repaired:
                    merged[fld] = repaired[fld]
            merged["name"] = orig_name  # double-protection
            updated_characters.append(merged)
        else:
            updated_characters.append(orig)

    # ---- Pass 3: re-critic (1 round) ----
    all_quality_warnings: list[str] = []
    try:
        recritic_input = json.dumps(
            {
                "characters": updated_characters,
                "ip_canon": canon_dict,
                "ip_must_have": list(ip_must_have or []),
                "era": era,
                "genre": genre,
                "world_description": description,
            },
            ensure_ascii=False,
        )
        recritic_text = await _collect_stream_text(
            llm_router,
            system=_HEAVY_CRITIC_CHARACTERS_SYSTEM,
            messages=[{"role": "user", "content": recritic_input}],
            max_tokens=2048,
        )
        recritic_data = _extract_json_from_text(recritic_text)
        if recritic_data and isinstance(recritic_data, dict):
            remaining_issues: list[dict] = [
                i for i in (recritic_data.get("issues") or []) if isinstance(i, dict)
            ]
            if remaining_issues and str(recritic_data.get("verdict", "ok")) == "needs_repair":
                all_quality_warnings = [
                    f"heavy_critic: target={i.get('target','')} kind={i.get('kind','')} detail={i.get('detail','')}"
                    for i in remaining_issues
                ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("heavy_critic_characters_recritic_failed", error=str(exc))

    return updated_characters, all_quality_warnings


_HEAVY_CRITIC_ENDINGS_SYSTEM = """你是互动叙事剧本的结局质量 critic。
审查给定的 endings 列表，结合 ip_must_have / era / genre / script_setting 判断：

- ip_canon_violation：strict 模式下，结局走向与原作主线 / 派系结局严重冲突（如原作中严党覆灭却写成严党称帝）
- era_anachronism：结局描述里出现明显跨朝代 / 跨题材的角色 / 道具 / 派系（嘉靖朝出现"叶赫那拉"、明朝出现"道长 / 仙人 / 法宝"等）
- genre_mismatch：结局违背 genre（历史正剧混入武侠 / 玄幻 / 异能元素）
- ip_must_have_orphan：strict 模式下，所有结局 description / condition 都没引用任何 ip_must_have 角色（结局跟原作锚点完全无关联）
- empty_or_duplicate：name / description / condition 为空，或多个结局描述高度相似
- condition_unclear：condition 字段语义模糊到 AI 主持人无法判断

输出严格 JSON：
{"verdict": "ok|needs_attention", "issues": [{"target": "ending name 或 索引", "kind": "问题类型", "detail": "具体描述"}]}

无问题输出：{"verdict": "ok", "issues": []}
只输出 JSON，不含任何解释文字。"""


async def heavy_critic_endings(
    endings: list[dict],
    script_setting: str,
    llm_router,
    *,
    era: str = "",
    genre: str = "",
    ip_must_have: list[str] | None = None,
    fidelity_mode: str = "none",
) -> list[str]:
    """对剧本 endings 做一次 review LLM，返回 quality_warnings 列表。

    不修复（结局 LLM 改起来风险高，留给 admin 决定）。
    失败 / 输入为空 → 返回 []，不阻断剧本生成。
    """
    if not endings:
        return []

    try:
        review_input = json.dumps(
            {
                "endings": endings,
                "script_setting": (script_setting or "")[:800],
                "era": era,
                "genre": genre,
                "fidelity_mode": fidelity_mode,
                "ip_must_have": list(ip_must_have or []),
            },
            ensure_ascii=False,
        )
        review_text = await _collect_stream_text(
            llm_router,
            system=_HEAVY_CRITIC_ENDINGS_SYSTEM,
            messages=[{"role": "user", "content": review_input}],
            max_tokens=1024,
        )
        review_data = _extract_json_from_text(review_text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("heavy_critic_endings_failed", error=str(exc))
        return []

    if not review_data or not isinstance(review_data, dict):
        return []
    issues = [i for i in (review_data.get("issues") or []) if isinstance(i, dict)]
    if not issues:
        return []
    return [
        f"heavy_critic_endings: target={i.get('target','')} kind={i.get('kind','')} detail={i.get('detail','')}"
        for i in issues
    ]


async def heavy_critic_playable(
    playable: list[dict],
    characters: list[dict],
    llm_router,
) -> tuple[list[dict], list[str]]:
    """playable review：检查每个 playable 是否在 characters 里、role 是否合理；不修复，只 review。

    返回 (playable, quality_warnings)
    失败 → (playable, [])
    """
    if not playable:
        return playable, []

    try:
        review_input = json.dumps(
            {
                "playable": playable,
                "characters": [{"name": c.get("name", ""), "role_tag": c.get("role_tag", "")} for c in characters],
            },
            ensure_ascii=False,
        )
        review_text = await _collect_stream_text(
            llm_router,
            system=_HEAVY_CRITIC_PLAYABLE_SYSTEM,
            messages=[{"role": "user", "content": review_input}],
            max_tokens=1024,
        )
        review_data = _extract_json_from_text(review_text)
        if not review_data or not isinstance(review_data, dict):
            return playable, []
        raw_warnings = review_data.get("warnings") or []
        warnings = [str(w) for w in raw_warnings if w]
        return playable, warnings
    except Exception as exc:  # noqa: BLE001
        logger.warning("heavy_critic_playable_failed", error=str(exc))
        return playable, []


# ---- 软分(LLM 整体打分,供异步质量打分器调用)----

_SOFT_SCORE_SYSTEM = """你是独立的互动叙事世界质量审计员。输入包含最终世界的审计投影、
冻结的 WorldSpec，以及研究证据。不要因为世界名称、文风或人物数量像原作就给高分，必须检查
角色身份、关系、地点归属、事件因果、时间线和 lore 正文。

打三个维度的分（各 1-10 整数）：
- ip_consistency：是否忠于指定 IP/版本；原创世界则看内部一致性与质感
- collision：角色是否有区分、没有功能撞车
- tension：可玩视角是否有信息差、行动空间和戏剧张力

发现问题时输出可定位 violation：
- severity=major：strict 复刻缺核心人物、用原创人物替换正典、版本/时代/身份/关键事件明显冲突
- severity=warning：同质化、细节可疑、证据不足或开放行动空间偏弱
- target 使用具体字段路径或实体名；detail 说明可执行的问题，不要泛泛而谈
- 研究材料不足时标 evidence_insufficient，不要凭空编造“正确答案”
- canon_characters 是可选正典池，不是全员必出；只有 must_have 缺失，或最终角色数低于 WorldSpec.scale 才算角色缺失
- relations_pack 是运行时最终关系图；其中 explicit 关系表达敌友亲疏，event_tied/trust=0 只表示共同经历、不得覆盖 explicit。任一处已有核心关系时，不得误报“关系缺失”
- code 只能从以下固定分类选择：canon_entity_missing、canon_identity_conflict、canon_relation_conflict、
  canon_event_conflict、timeline_causality_conflict、lore_conflict、location_conflict、duplicate_content、
  role_homogenization、text_corruption、evidence_insufficient、gameplay_weakness、other_quality_issue

输出严格 JSON：
{"ip_consistency":int,"collision":int,"tension":int,"confidence":0到1小数,
 "violations":[{"code":"snake_case","severity":"major|warning","target":"路径或实体","detail":"具体问题"}],
 "summary":"整体质量与最大短板"}"""


def _clamp_score(v: object) -> int | None:
    try:
        return max(1, min(10, int(v)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _median_int(values: list[int]) -> int | None:
    """整数中位数（偶数个取偏低的中点，对"是否触底"判定更保守）。"""
    vs = sorted(values)
    if not vs:
        return None
    mid = (len(vs) - 1) // 2
    return vs[mid]


_QUALITY_CODES = {
    "canon_entity_missing",
    "canon_identity_conflict",
    "canon_relation_conflict",
    "canon_event_conflict",
    "timeline_causality_conflict",
    "lore_conflict",
    "location_conflict",
    "duplicate_content",
    "role_homogenization",
    "text_corruption",
    "evidence_insufficient",
    "gameplay_weakness",
    "other_quality_issue",
}


def _normalize_quality_code(raw: object) -> str:
    code = re.sub(r"[^a-z0-9_]+", "_", str(raw or "").lower()).strip("_")
    if code in _QUALITY_CODES:
        return code
    if "evidence" in code or "citation" in code:
        return "evidence_insufficient"
    if "text" in code or "garbl" in code or "language" in code:
        return "text_corruption"
    if "relation" in code or "peer" in code or "parent_child" in code:
        return "canon_relation_conflict"
    if "location" in code or "place" in code:
        return "location_conflict"
    if "lore" in code:
        return "lore_conflict"
    if "duplicate" in code or "duplication" in code:
        return "duplicate_content"
    if "event" in code or "timeline" in code or "causality" in code or "plot" in code:
        return "timeline_causality_conflict"
    if "missing" in code and any(term in code for term in ("canon", "character", "entity", "core", "key")):
        return "canon_entity_missing"
    if any(term in code for term in ("identity", "faction", "affiliation", "canon_conflict")):
        return "canon_identity_conflict"
    if "homogen" in code or "collision" in code:
        return "role_homogenization"
    if "playable" in code or "gameplay" in code or "tension" in code:
        return "gameplay_weakness"
    return "other_quality_issue"


async def _score_world_soft_once(score_input: str, llm_router) -> dict | None:
    """单次软评分。失败/坏 JSON → None。"""
    try:
        text = await _collect_stream_text(
            llm_router,
            system=_SOFT_SCORE_SYSTEM,
            messages=[{"role": "user", "content": score_input}],
            max_tokens=1024,
        )
        data = _extract_json_from_text(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("score_world_soft_once_failed", error=str(exc))
        return None
    if not data or not isinstance(data, dict):
        return None
    violations: list[dict] = []
    for item in data.get("violations") or []:
        if not isinstance(item, dict):
            continue
        code = _normalize_quality_code(item.get("code"))
        severity = str(item.get("severity") or "warning").lower()
        violations.append(
            {
                "code": code,
                "severity": "major" if severity == "major" else "warning",
                "target": str(item.get("target") or "")[:200],
                "detail": str(item.get("detail") or "")[:800],
            }
        )
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    return {
        "ip_consistency": _clamp_score(data.get("ip_consistency")),
        "collision": _clamp_score(data.get("collision")),
        "tension": _clamp_score(data.get("tension")),
        "confidence": confidence,
        "violations": violations[:12],
        "summary": str(data.get("summary", ""))[:500],
    }


def _clip(value: object, limit: int) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            text = str(value or "")
    return text[:limit]


def _quality_audit_projection(
    payload: dict,
    ip_pack: dict | None,
    world_spec: dict | None,
) -> dict:
    """Bounded semantic projection of every canon-bearing world section."""
    characters = []
    for char in (payload.get("world_characters") or [])[:40]:
        if not isinstance(char, dict):
            continue
        characters.append(
            {
                "name": char.get("name"),
                "role_tag": char.get("role_tag"),
                "faction": char.get("faction"),
                "playable": bool(char.get("playable_role") or char.get("playable")),
                "description": _clip(char.get("description"), 260),
                "personality": _clip(char.get("personality"), 140),
                "secret": _clip(char.get("secret"), 180),
                "voice_style": _clip(char.get("voice_style"), 120),
                "knowledge": [_clip(item, 140) for item in (char.get("knowledge") or [])[:3]],
                "initial_location": char.get("initial_location"),
                "schedule": dict(list((char.get("schedule") or {}).items())[:4]),
                "initial_peer_relations": [
                    {
                        "target": item.get("target"),
                        "kind": item.get("kind"),
                        "trust": item.get("trust"),
                    }
                    for item in (char.get("initial_peer_relations") or [])[:6]
                    if isinstance(item, dict)
                ],
                "runtime_relations": [
                    {
                        "target": item.get("target"),
                        "kind": item.get("kind"),
                        "trust": item.get("trust"),
                        "why": item.get("why"),
                    }
                    for item in (
                        ((payload.get("relations_pack") or {}).get("relations_by_npc") or {}).get(
                            char.get("name"), []
                        )
                    )[:12]
                    if isinstance(item, dict)
                ],
            }
        )

    locations = [
        {"name": item.get("name"), "description": _clip(item.get("description"), 260)}
        for item in (payload.get("locations") or [])[:24]
        if isinstance(item, dict)
    ]
    shared_events = [
        {
            "id": item.get("id"),
            "title": item.get("title") or item.get("name"),
            "summary": _clip(item.get("summary") or item.get("description"), 420),
            "involved_npcs": list(item.get("involved_npcs") or [])[:12],
            "perceptions": _clip(item.get("perceptions"), 600),
        }
        for item in (payload.get("shared_events") or [])[:20]
        if isinstance(item, dict)
    ]
    events_data = [
        {
            "id": item.get("id"),
            "kind": item.get("kind"),
            "title": item.get("title") or item.get("name"),
            "summary": _clip(item.get("summary") or item.get("description"), 320),
            "trigger": item.get("trigger") or {},
            "effects": item.get("effects") or {},
            "rumors": (item.get("rumors") or [])[:6],
            "disabled": bool(item.get("disabled")),
        }
        for item in (payload.get("events_data") or [])[:16]
        if isinstance(item, dict)
    ]

    lore_dimensions = []
    for dimension in ((payload.get("lore_pack") or {}).get("dimensions") or [])[:6]:
        if not isinstance(dimension, dict):
            continue
        lore_dimensions.append(
            {
                "name": dimension.get("name"),
                "blocks": [
                    {
                        "heading": block.get("heading"),
                        "body": _clip(block.get("body"), 420),
                    }
                    for block in (dimension.get("content_blocks") or [])[:4]
                    if isinstance(block, dict)
                ],
            }
        )

    pack = ip_pack or {}
    research = {
        "ip_name": pack.get("ip_name"),
        "fidelity_mode": pack.get("fidelity_mode"),
        "canon_note": _clip(pack.get("canon_note"), 500),
        "summary": _clip(pack.get("summary"), 1600),
        "characters": [
            {
                "name": item.get("name"),
                "role": _clip(item.get("role_in_story"), 180),
                "relation_to_protagonist": _clip(item.get("relation_to_protagonist"), 140),
                "story_arc": _clip(item.get("story_arc"), 260),
                "must_have": bool(item.get("must_have")),
                "in_continuity": item.get("in_continuity", True),
            }
            for item in (pack.get("characters") or [])[:40]
            if isinstance(item, dict)
        ],
        "places": [
            {"name": item.get("name"), "description": _clip(item.get("description"), 180)}
            for item in (pack.get("places") or [])[:24]
            if isinstance(item, dict)
        ],
        "key_events": [
            {"name": item.get("name"), "description": _clip(item.get("description"), 220)}
            for item in (pack.get("key_events") or [])[:20]
            if isinstance(item, dict)
        ],
        "timeline": [
            {"when": item.get("when"), "event": _clip(item.get("event"), 260)}
            for item in (pack.get("timeline") or [])[:20]
            if isinstance(item, dict)
        ],
        "evidence_excerpt": [
            {
                "id": item.get("id"),
                "source": item.get("source"),
                "citations": [
                    str(tag)[len("citation:") :]
                    for tag in (item.get("tags") or [])
                    if str(tag).startswith("citation:")
                ][:5],
                "text": _clip(item.get("text"), 1000),
            }
            for item in (pack.get("passages") or [])[:2]
            if isinstance(item, dict)
        ],
    }
    return {
        "world_spec": world_spec or {},
        "world": {
            "name": payload.get("name"),
            "description": _clip(payload.get("description"), 1400),
            "base_setting": _clip(payload.get("base_setting"), 2200),
            "free_setting": _clip(payload.get("free_setting"), 1200),
            "characters": characters,
            "locations": locations,
            "shared_events": shared_events,
            "events_data": events_data,
            "lore_dimensions": lore_dimensions,
        },
        "research": research,
    }


def _merge_quality_violations(
    runs: list[dict], *, require_consensus: bool,
) -> tuple[list[dict], list[dict]]:
    grouped: dict[tuple[str, str], dict] = {}
    for run in runs:
        seen: set[tuple[str, str]] = set()
        for item in run.get("violations") or []:
            key = (str(item.get("code") or "other_quality_issue"), "")
            if key in seen:
                continue
            seen.add(key)
            current = grouped.setdefault(key, {**item, "votes": 0})
            current["votes"] += 1
            if item.get("severity") == "major":
                current["severity"] = "major"
    confirmed = [
        item
        for item in grouped.values()
        if item["votes"] >= 2 or (len(runs) == 1 and not require_consensus)
    ]
    unconfirmed = [item for item in grouped.values() if item not in confirmed]
    return confirmed, unconfirmed


async def score_world_soft(
    payload: dict,
    ip_canon: dict | None,
    llm_router,
    *,
    world_spec: dict | None = None,
    vote: int | None = None,
) -> dict | None:
    """Adaptive soft review: normally one judge, escalate only on risk.

    ``vote`` remains as a compatibility/testing override.  Without it we run a
    second judge only for blocking/borderline output, and a third only when the
    first two materially disagree.  This replaces the unconditional 3-call
    quality tax while retaining protection where a false decision matters.
    """
    score_input = json.dumps(
        _quality_audit_projection(payload, ip_canon, world_spec),
        ensure_ascii=False,
    )

    require_consensus = bool(vote and vote > 1)
    required_names = {
        re.sub(r"[\s·•・]", "", str(name or "")).strip()
        for name in (world_spec or {}).get("must_have_characters", [])
        if str(name or "").strip()
    }
    present_names = {
        re.sub(r"[\s·•・]", "", str(item.get("name") or "")).strip()
        for item in (payload.get("world_characters") or [])
        if isinstance(item, dict) and item.get("name")
    }
    missing_required = required_names - present_names
    target_count = int(((world_spec or {}).get("scale") or {}).get("active_roles_target") or 0)
    scale_satisfied = target_count <= 0 or len(present_names) >= target_count

    def _apply_contract(run: dict | None) -> dict | None:
        if run is None or missing_required or not scale_satisfied:
            return run
        # canon_characters is an eligible source pool, while must_have is the
        # required set.  A judge cannot promote an optional omission to major
        # when the frozen scale and must-have contract are both satisfied.
        for item in run.get("violations") or []:
            if item.get("code") == "canon_entity_missing" and item.get("severity") == "major":
                item["severity"] = "warning"
        return run

    if vote is not None:
        n = max(1, vote)
        results = await asyncio.gather(
            *[_score_world_soft_once(score_input, llm_router) for _ in range(n)]
        )
        runs = [normalized for r in results if (normalized := _apply_contract(r))]
    else:
        first = _apply_contract(await _score_world_soft_once(score_input, llm_router))
        runs = [first] if first else []
        dims = ("ip_consistency", "collision", "tension")
        first_major = any(
            item.get("severity") == "major" for item in (first or {}).get("violations", [])
        )
        borderline = (
            first is None
            or any(not isinstance(first.get(k), int) or first[k] <= 6 for k in dims)
            or first_major
            or float(first.get("confidence", 0.0)) < 0.65
        )
        require_consensus = borderline
        if borderline:
            second = _apply_contract(await _score_world_soft_once(score_input, llm_router))
            if second:
                runs.append(second)
            first_major_keys = {
                item.get("code")
                for item in (first or {}).get("violations", [])
                if item.get("severity") == "major"
            }
            second_major_keys = {
                item.get("code")
                for item in (second or {}).get("violations", [])
                if item.get("severity") == "major"
            }
            disagree = bool(
                first and second and any(
                    isinstance(first.get(k), int)
                    and isinstance(second.get(k), int)
                    and abs(first[k] - second[k]) >= 2
                    for k in dims
                )
            ) or bool(first and second and first_major_keys != second_major_keys)
            if disagree:
                third = _apply_contract(await _score_world_soft_once(score_input, llm_router))
                if third:
                    runs.append(third)
        n = len(runs)
    if not runs:
        return None

    def _median_dim(key: str) -> int | None:
        return _median_int([r[key] for r in runs if isinstance(r.get(key), int)])

    ip_med = _median_dim("ip_consistency")
    col_med = _median_dim("collision")
    ten_med = _median_dim("tension")
    # summary 取 ip_consistency 最接近中位的那次（与门控维度对齐）。
    if ip_med is not None:
        best = min(
            (r for r in runs if isinstance(r.get("ip_consistency"), int)),
            key=lambda r: abs(r["ip_consistency"] - ip_med),
            default=runs[0],
        )
    else:
        best = runs[0]

    confirmed, unconfirmed = _merge_quality_violations(
        runs, require_consensus=require_consensus,
    )
    confidence_values = [float(run.get("confidence", 0.0)) for run in runs]
    confidence = sorted(confidence_values)[(len(confidence_values) - 1) // 2]
    logger.info(
        "score_world_soft_voted",
        votes=len(runs),
        of=n,
        adaptive=vote is None,
        ip_consistency=ip_med,
        collision=col_med,
        tension=ten_med,
    )
    return {
        "ip_consistency": ip_med,
        "collision": col_med,
        "tension": ten_med,
        "confidence": confidence,
        "violations": confirmed + unconfirmed,
        "confirmed_violations": confirmed,
        "unconfirmed_violations": unconfirmed,
        "summary": best.get("summary", ""),
        "judge_count": len(runs),
    }
