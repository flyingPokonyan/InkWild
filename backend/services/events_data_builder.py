"""events_data_builder — LLM 生成 events_data: list[EventDataEntry]。

分批生成（≤batch_size events / 批），并发 concurrency 路。
每条 event 生成后逐条校验：
  1. condition_dsl 能被 engine.condition_dsl.parse 接受，否则 disabled=true
  2. trigger.npc_name (npc_intent_driven) 必须在 characters 列表中，否则 disabled=true
  3. rumors[].knower_npcs 中不在 characters 的丢弃
  4. effects.npc_mood_changes 中不在 characters 的 keys 丢弃

单批失败不阻塞其他批（asyncio.gather return_exceptions=True）。
总产出 dedup by id（取第一个出现的）。
"""
from __future__ import annotations

import asyncio
import json
import math
from typing import Any

import structlog

from engine.condition_dsl import ConditionDSLParseError, parse as dsl_parse
from schemas.character_v2 import Character
from schemas.events_data import EventDataEntry, EventEffects, EventRumor
from schemas.lore_pack import LorePack
from schemas.research_pack import IPCanon
from schemas.shared_events import SharedEvent

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """你是一个互动叙事世界的事件设计师。
你的任务是为给定世界设计真实可信的事件（events_data），
每个事件须符合世界背景、人物关系和已有历史。
严格按照要求输出 JSON，不包含任何解释或 markdown。"""


def _build_user_prompt(
    description: str,
    ip_canon: IPCanon,
    characters: list[Character],
    locations: list[str],
    shared_events: list[SharedEvent],
    lore_pack: LorePack,
    existing_ids: list[str],
    batch_n: int,
    *,
    ip_pack: object | None = None,
    fidelity_mode: str = "none",
) -> str:
    """构建单批 LLM user prompt。"""
    char_names = [c.name for c in characters]

    lore_summary = ""
    if lore_pack.dimensions:
        parts = []
        for dim in lore_pack.dimensions[:3]:  # 取前3个维度摘要
            block_texts = [b.heading for b in dim.content_blocks[:2]]
            parts.append(f"{dim.name}: {', '.join(block_texts)}")
        lore_summary = "; ".join(parts)

    shared_summary = ""
    if shared_events:
        shared_summary = ", ".join(e.title for e in shared_events[:5])

    ip_info = ""
    if ip_canon.title_guesses:
        ip_info = f"IP背景参考: {', '.join(ip_canon.title_guesses[:2])}"

    # IP fidelity block — only when pack is present + strict/loose
    ip_fidelity_block = ""
    if ip_pack is not None and fidelity_mode in ("strict", "loose"):
        must_have = getattr(ip_pack, "must_have_character_names", lambda: [])()
        header = (
            "【强约束·原作锚点】" if fidelity_mode == "strict"
            else "【参考·原作锚点】"
        )
        directive = (
            "事件应推进或穿插原作核心冲突；npc_intent_driven 类事件优先挂在以下原作角色身上："
            if fidelity_mode == "strict"
            else "事件可借鉴原作冲突；可在原作角色身上挂事件以增强氛围："
        )
        if must_have:
            ip_fidelity_block = (
                f"\n{header}\n"
                f"原作《{getattr(ip_pack, 'ip_name', '')}》必备角色：{', '.join(must_have)}\n"
                f"{directive}\n"
            )

    existing_note = ""
    if existing_ids:
        existing_note = f"\n已存在的事件ID（不要重复）: {', '.join(existing_ids)}"

    return f"""世界描述:
{description}

{ip_info}{ip_fidelity_block}

可用角色（名字列表）:
{json.dumps(char_names, ensure_ascii=False)}

可用地点列表:
{json.dumps(locations, ensure_ascii=False)}

重要历史事件参考:
{shared_summary or '（无）'}

世界观深度内容:
{lore_summary or '（无）'}
{existing_note}

请生成 {batch_n} 个不同类型的 events_data 条目，输出严格 JSON（不含 markdown）：
{{
  "events": [
    {{
      "id": "唯一字符串ID（统一前缀 evt_，例如 evt_001）",
      "kind": "conditional" 或 "npc_intent_driven",
      "summary": "事件简述",
      "trigger": {{
        // condition_tree 是结构化条件树（必填）。形态如下：
        //   时间/地点/动作判断: {{"op":"func","name":"time_after","args":["day_3"]}}
        //                       name 可选: "time_after" | "location_is" | "player_did"
        //   字段比较:          {{"op":"==","left":{{"field":"world_state.<key>"}},"right":true}}
        //                       op 可选: "==" "!=" ">=" "<=" ">" "<"
        //                       right 可以是 true/false/数字 或 {{"field":"world_state.<key>"}}
        //   组合:              {{"op":"AND","operands":[<节点>,<节点>,...]}}（>=2 项）
        //                       {{"op":"OR","operands":[...]}}
        //                       {{"op":"NOT","operand":<节点>}}
        // 若 kind=conditional: {{"condition_tree": {{...}}, "probability": 0.8}}
        // 若 kind=npc_intent_driven: {{"npc_name": "角色名", "condition_tree": {{...}}, "intent_payload": {{}}}}
      }},
      "effects": {{
        "world_state_changes": {{}},
        "spawn_clues": [],
        "npc_mood_changes": {{}}
      }},
      "rumors": [
        {{"text": "谣言内容", "knower_npcs": ["角色名"]}}
      ]
    }}
  ]
}}

condition_tree 正确示例（直接复制结构）：
  时间过 day_3：{{"op":"func","name":"time_after","args":["day_3"]}}
  发现真相标记：{{"op":"==","left":{{"field":"world_state.discovered_truth"}},"right":true}}
  两个条件都满足：{{"op":"AND","operands":[
    {{"op":"func","name":"time_after","args":["day_3"]}},
    {{"op":"==","left":{{"field":"world_state.met_lead"}},"right":true}}
  ]}}
  不在密室：{{"op":"NOT","operand":{{"op":"func","name":"location_is","args":["密室"]}}}}

禁止写法：不要输出 condition_dsl 字符串；不要写裸标记 "world_state.x AND world_state.y"；
不要用 AND(x,y) 函数式语法；不要在条件中使用未在 world_state 出现过的键。
npc_name 和 knower_npcs 必须使用上面角色列表中的名字。"""


# ---------------------------------------------------------------------------
# Helpers (reused from research_pack_builder pattern)
# ---------------------------------------------------------------------------


async def _collect_stream_text(
    llm_router: Any,
    *,
    system: str,
    messages: list[dict],
    max_tokens: int,
) -> str:
    """通过 stream_with_tools(tools=[]) 收集纯文本输出。"""
    parts: list[str] = []
    async for event in llm_router.stream_with_tools(
        messages=messages,
        tools=[],
        system=system,
        max_tokens=max_tokens,
    ):
        if event.get("type") == "text_delta":
            parts.append(event.get("text", ""))
    return "".join(parts).strip()


def _extract_json_from_text(text: str) -> dict | None:
    """从 LLM 返回文本中提取 JSON 对象，兼容 Markdown 代码块包裹。"""
    candidates = [text]
    if "```json" in text:
        for part in text.split("```json")[1:]:
            candidates.append(part.split("```", 1)[0].strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{") : text.rfind("}") + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _coerce_spawn_clues(raw: list) -> list[str]:
    """LLM sometimes emits ``{clue_id, description, location}`` dicts instead
    of the schema's plain strings. Flatten dicts to a representative text
    (prefer ``description``); ignore non-string / empty entries.
    """
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(
                item.get("description")
                or item.get("text")
                or item.get("clue_id")
                or ""
            ).strip()
        else:
            continue
        if text:
            out.append(text)
    return out


def _validate_event(raw: dict, char_names: set[str]) -> EventDataEntry:
    """解析并校验单条 event raw dict，返回 EventDataEntry（disabled 按需设 true）。"""
    eid = str(raw.get("id", ""))
    kind = raw.get("kind", "conditional")
    summary = str(raw.get("summary", ""))
    trigger = raw.get("trigger") or {}
    raw_effects = raw.get("effects") or {}
    raw_rumors = raw.get("rumors") or []

    disabled = False
    disabled_reason = ""

    # -- 1. validate condition (prefer structured tree; fall back to legacy string for compat) --
    from engine.condition_tree import (
        ConditionTreeError,
        serialize_to_dsl,
        validate_tree,
    )

    condition_tree = trigger.get("condition_tree")
    condition_dsl_str = trigger.get("condition_dsl", "")

    if isinstance(condition_tree, dict):
        tree_issues = validate_tree(condition_tree)
        if tree_issues:
            disabled = True
            disabled_reason = f"condition_tree_invalid: {tree_issues[0]}"
            logger.warning(
                "events_data_tree_invalid",
                event_id=eid,
                issues=tree_issues,
            )
        else:
            try:
                condition_dsl_str = serialize_to_dsl(condition_tree)
                trigger["condition_dsl"] = condition_dsl_str
                # condition_tree retained in trigger for audit / future migration.
            except ConditionTreeError as exc:
                disabled = True
                disabled_reason = f"condition_tree_serialize_error: {exc}"
                logger.warning(
                    "events_data_tree_serialize_error",
                    event_id=eid,
                    error=str(exc),
                )
    else:
        # Legacy path: LLM still produced a DSL string. Validate strictly —
        # the previous bare-flag normalizer has been removed at the generator
        # boundary, so any malformed string disables the event.
        try:
            dsl_parse(condition_dsl_str)
        except (ConditionDSLParseError, Exception) as exc:
            disabled = True
            disabled_reason = f"dsl_parse_error: {exc}"
            logger.warning(
                "events_data_dsl_parse_error",
                event_id=eid,
                dsl=condition_dsl_str,
                error=str(exc),
            )

    # -- 2. validate npc_name for npc_intent_driven --
    if not disabled and kind == "npc_intent_driven":
        npc_name = trigger.get("npc_name", "")
        if npc_name not in char_names:
            disabled = True
            disabled_reason = f"invalid_npc_name: {npc_name!r} not in characters"
            logger.warning(
                "events_data_invalid_npc_name",
                event_id=eid,
                npc_name=npc_name,
            )

    # -- 3. filter rumors knower_npcs --
    filtered_rumors: list[EventRumor] = []
    for r in raw_rumors:
        text = str(r.get("text", ""))
        knowers = [n for n in (r.get("knower_npcs") or []) if n in char_names]
        filtered_rumors.append(EventRumor(text=text, knower_npcs=knowers))

    # -- 4. filter npc_mood_changes keys --
    raw_mood = raw_effects.get("npc_mood_changes") or {}
    filtered_mood = {k: v for k, v in raw_mood.items() if k in char_names}

    effects = EventEffects(
        world_state_changes=raw_effects.get("world_state_changes") or {},
        spawn_clues=_coerce_spawn_clues(raw_effects.get("spawn_clues") or []),
        npc_mood_changes=filtered_mood,
    )

    return EventDataEntry(
        id=eid,
        kind=kind,  # type: ignore[arg-type]
        summary=summary,
        trigger=trigger,
        effects=effects,
        rumors=filtered_rumors,
        disabled=disabled,
        disabled_reason=disabled_reason,
    )


# ---------------------------------------------------------------------------
# Single-batch generation
# ---------------------------------------------------------------------------


async def _generate_batch(
    batch_idx: int,
    batch_n: int,
    description: str,
    ip_canon: IPCanon,
    characters: list[Character],
    locations: list[str],
    shared_events: list[SharedEvent],
    lore_pack: LorePack,
    existing_ids: list[str],
    llm_router: Any,
    char_names: set[str],
    *,
    ip_pack: object | None = None,
    fidelity_mode: str = "none",
) -> list[EventDataEntry]:
    """生成单批 events，返回校验后的 EventDataEntry 列表。单批异常向上抛。"""
    user_prompt = _build_user_prompt(
        description=description,
        ip_canon=ip_canon,
        characters=characters,
        locations=locations,
        shared_events=shared_events,
        lore_pack=lore_pack,
        existing_ids=existing_ids,
        batch_n=batch_n,
        ip_pack=ip_pack,
        fidelity_mode=fidelity_mode,
    )

    text = await _collect_stream_text(
        llm_router,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        # 8192: 一批多个含 condition_tree+rumors 的事件 JSON 较大，6144 易截断 →
        # 整批 JSON 解析失败被静默丢弃（事件数骤减）。留足余量。(2026-05-31)
        max_tokens=8192,
    )

    data = _extract_json_from_text(text)
    if data is None:
        logger.warning(
            "events_data_batch_json_parse_failed",
            batch_idx=batch_idx,
            text_preview=text[:200],
        )
        return []

    raw_events = data.get("events") or []
    if not isinstance(raw_events, list):
        logger.warning("events_data_batch_not_list", batch_idx=batch_idx)
        return []

    results: list[EventDataEntry] = []
    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        try:
            entry = _validate_event(raw, char_names)
            results.append(entry)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "events_data_entry_parse_error",
                batch_idx=batch_idx,
                error=str(exc),
                raw=raw,
            )
    return results


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------


async def build_events_data(
    description: str,
    ip_canon: IPCanon,
    characters: list[Character],
    locations: list[str],
    shared_events: list[SharedEvent],
    lore_pack: LorePack,
    llm_router: Any,
    *,
    target_count: int = 8,
    # batch_size 3（原 5）：每批 JSON 更小，配合 max_tokens=8192 几乎不会因截断
    # 导致整批解析失败丢弃。target 8 → 3 批(3+3+2)，concurrency 3 一轮并发，零额外延迟。
    batch_size: int = 3,
    concurrency: int = 3,
    ip_pack: object | None = None,
    fidelity_mode: str = "none",
) -> list[EventDataEntry]:
    """LLM 分批生成 events_data，并发 concurrency 路，返回校验后的 EventDataEntry 列表。

    - 单批失败（LLM 异常 / JSON 解析失败）不阻塞其他批
    - 总产出 dedup by id（取第一个出现的）
    """
    char_names: set[str] = {c.name for c in characters}

    # 切批：⌈target_count / batch_size⌉ 批
    num_batches = math.ceil(target_count / batch_size) if target_count > 0 else 0
    if num_batches == 0:
        return []

    # 每批目标数量：最后一批可能少于 batch_size
    batch_counts: list[int] = []
    remaining = target_count
    for _ in range(num_batches):
        n = min(batch_size, remaining)
        batch_counts.append(n)
        remaining -= n

    # 串行按 concurrency 分组并发
    all_results: list[EventDataEntry] = []
    existing_ids: list[str] = []

    for group_start in range(0, num_batches, concurrency):
        group = batch_counts[group_start : group_start + concurrency]

        coros = [
            _generate_batch(
                batch_idx=group_start + i,
                batch_n=group[i],
                description=description,
                ip_canon=ip_canon,
                characters=characters,
                locations=locations,
                shared_events=shared_events,
                lore_pack=lore_pack,
                existing_ids=list(existing_ids),
                llm_router=llm_router,
                char_names=char_names,
                ip_pack=ip_pack,
                fidelity_mode=fidelity_mode,
            )
            for i in range(len(group))
        ]

        results = await asyncio.gather(*coros, return_exceptions=True)

        for i, result in enumerate(results):
            batch_idx = group_start + i
            if isinstance(result, BaseException):
                logger.warning(
                    "events_data_batch_failed",
                    batch_idx=batch_idx,
                    error=str(result),
                )
                continue
            for entry in result:
                all_results.append(entry)
                existing_ids.append(entry.id)

    # Dedup by id (take first occurrence)
    seen_ids: set[str] = set()
    deduped: list[EventDataEntry] = []
    for entry in all_results:
        if entry.id not in seen_ids:
            seen_ids.add(entry.id)
            deduped.append(entry)

    return deduped
