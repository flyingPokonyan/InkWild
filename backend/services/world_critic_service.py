"""World critic 分级（spec §5）：
- validate_world_shape: 形状 + 引用一致性，无 LLM
- light_critic_lore / light_critic_shared_events: 单 LLM pass 写 quality_warnings 不修复
- heavy_critic_characters: 重 critic，含 review + repair pass（v1 同质量）
- heavy_critic_playable: playable review，只检不修
"""
from __future__ import annotations

import json
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
    original_name_map = {c["name"]: c for c in characters if c.get("name")}
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

_SOFT_SCORE_SYSTEM = """你是互动叙事世界的质量评审。对给定世界打三个维度的分(各 1-10 整数)：
- ip_consistency：是否忠于所复刻 IP / 设定自洽（原创世界看设定内部一致性与质感）
- collision：角色是否各有区分、不功能撞车、不雷同（分越高越好）
- tension：可玩视角是否有信息差与行动空间、戏剧张力够不够
再给一句 summary 概括整体质量与最大短板。
输出严格 JSON：{"ip_consistency":int,"collision":int,"tension":int,"summary":str}"""


async def score_world_soft(payload: dict, ip_canon: dict | None, llm_router) -> dict | None:
    """对最终 world payload 跑一次 LLM 软评分。失败返回 None(打分器据此跳过软分,不阻断)。

    仅单次质量参考,不进纵向趋势(软分换模型/prompt 不可比,见 plan 决策①)。
    """
    try:
        chars = payload.get("world_characters") or []
        brief_chars = [
            {
                "name": c.get("name"),
                "playable": bool(c.get("playable")),
                "description": str(c.get("description", ""))[:200],
                "personality": str(c.get("personality", ""))[:120],
            }
            for c in chars if isinstance(c, dict)
        ]
        score_input = json.dumps(
            {
                "name": payload.get("name"),
                "base_setting": str(payload.get("base_setting", ""))[:1500],
                "characters": brief_chars,
                "ip_canon": ip_canon or {},
            },
            ensure_ascii=False,
        )
        text = await _collect_stream_text(
            llm_router,
            system=_SOFT_SCORE_SYSTEM,
            messages=[{"role": "user", "content": score_input}],
            max_tokens=1024,
        )
        data = _extract_json_from_text(text)
        if not data or not isinstance(data, dict):
            return None

        def _clamp(v: object) -> int | None:
            try:
                return max(1, min(10, int(v)))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None

        return {
            "ip_consistency": _clamp(data.get("ip_consistency")),
            "collision": _clamp(data.get("collision")),
            "tension": _clamp(data.get("tension")),
            "summary": str(data.get("summary", ""))[:500],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("score_world_soft_failed", error=str(exc))
        return None
