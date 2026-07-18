"""SharedEvents builder — 从 ResearchPack.passages 提取共享历史事件。

公共 API：
  build_shared_events(description, ip_canon, characters, passages, llm_router, ...)
    → list[SharedEvent]

实现思路：
  1. 第一步：单 LLM 调用，从 passages 抽取 shared events（含 source_passage_ids）
  2. 第二步：校验 + 过滤（source_passage_ids / involved_npcs 必须在输入集合中）
  3. 若条数 < k_min，再次 LLM 补到 k_min（无 passage 依据，source_passage_ids=[]）
  4. 第三步：title 去重（同 title 取后者）
  5. 失败 fallback：返回已抽到的（可能为空 list），不抛错
"""
from __future__ import annotations

from typing import Any

import structlog

from schemas.character_v2 import Character
from schemas.ip_knowledge_pack import FidelityMode, IPKnowledgePack
from schemas.research_pack import IPCanon, Passage
from schemas.shared_events import SharedEvent, SharedEventPerception
from services.research_pack_builder import _collect_stream_text, _extract_json_from_text

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """你是世界叙事设计师。根据给定的世界描述、IP 信息、角色名单和研究原文片段，
提取对这个世界中 NPC 共同参与或共同知晓的历史事件（shared events）。

输出要求：
- 严格 JSON，格式：{"events": [{...}, ...]}
- 每条 event 字段：id（字符串）、title（简短标题）、summary（200字以内摘要）、
  era（时代/时间段，可空）、involved_npcs（从角色名单里选，不得编造）、
  perceptions（必填，dict，key 为 NPC name）、source_passage_ids（从给定 passage id 里选，不得编造）
- source_passage_ids 必须来自提供的 passage id 列表，不能编造不存在的 id
- involved_npcs 必须来自提供的角色名单，不能编造不存在的角色
- 每条事件为 2-4 名相关角色填写 perceptions，分别写 knows / believes / feels；至少制造一处
  “所知不同”或“信念不同”，不能所有角色都看到同一份摘要
- **必须**输出 **至少 3 条** shared events；如果上方提供了 IP 上下文（已识别 IP、key_events、factions 等），
  目标条数应在 5-15 之间，并优先以 IP 的 key_events / timeline / factions 为锚点生成
- **不允许**返回空数组；即使原文 passages 信息有限，也要基于世界描述与角色名单合理构建
- 不要输出解释文字，只输出 JSON"""

_SUPPLEMENT_SYSTEM = """你是世界叙事设计师。已有部分共享事件，请在不依赖具体原文的情况下，
根据世界描述和 IP 信息额外创作更多共享历史事件，补足数量到指定目标。

输出要求：
- 严格 JSON，格式：{"events": [{...}, ...]}
- 每条 event 字段同上，source_passage_ids 必须为空列表 []（无原文依据）
- involved_npcs 必须来自给定的角色名单
- perceptions 必填：每条为 2-4 名相关角色写不同的 knows / believes / feels
- 不要重复已有事件的 title
- 必须补足到指定数量，不允许返回空数组
- 只输出 JSON"""


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _build_ip_pack_block(
    ip_pack: IPKnowledgePack | None,
    fidelity_mode: FidelityMode,
) -> str:
    """构建注入到 user prompt 的 IP 上下文块（仅在 strict / loose + 非空 pack 时返回非空字符串）。"""
    if ip_pack is None or fidelity_mode not in ("strict", "loose"):
        return ""

    summary_excerpt = (ip_pack.summary or "").strip()[:500]
    char_names = [c.name for c in ip_pack.canon_characters()[:8] if getattr(c, "name", "")]
    place_names = [p.name for p in ip_pack.places[:8] if getattr(p, "name", "")]
    faction_names = [f.name for f in ip_pack.factions[:8] if getattr(f, "name", "")]
    object_names = [o.name for o in ip_pack.iconic_objects[:8] if getattr(o, "name", "")]
    event_lines = [
        f"- {e.name}: {(e.description or '').strip()[:120]}"
        for e in ip_pack.key_events[:10]
        if getattr(e, "name", "")
    ]

    block = (
        f"\n=== 已识别 IP 上下文（fidelity={fidelity_mode}）===\n"
        f"IP 名：{ip_pack.ip_name}（{ip_pack.ip_type}）\n"
    )
    if summary_excerpt:
        block += f"原作摘要：{summary_excerpt}\n"
    if char_names:
        block += f"核心角色：{', '.join(char_names)}\n"
    if place_names:
        block += f"标志性地点：{', '.join(place_names)}\n"
    if faction_names:
        block += f"派系势力：{', '.join(faction_names)}\n"
    if object_names:
        block += f"标志性器物：{', '.join(object_names)}\n"
    if event_lines:
        block += "关键事件（key_events）：\n" + "\n".join(event_lines) + "\n"
    block += (
        "提示：以上属于真实存在的 IP 世界。请以这些 key_events / factions / 角色关系为锚点，"
        "构建 NPC 共同参与或共同知晓的历史事件。**至少输出 5 条 shared events**，"
        "其中尽量覆盖关键事件以保证忠于原作。\n"
    )
    return block


def _build_extract_prompt(
    description: str,
    ip_canon: IPCanon,
    characters: list[Character],
    passages: list[Passage],
    k_target: int,
    *,
    ip_pack: IPKnowledgePack | None = None,
    fidelity_mode: FidelityMode = "none",
) -> str:
    """构建从 passages 提取 shared events 的 user prompt。"""
    char_names = [c.name for c in characters]
    passage_lines = "\n".join(
        f"[{p.id}] {p.text}" for p in passages
    )
    ip_info = ""
    if ip_canon.title_guesses or ip_canon.canonical_names:
        ip_info = (
            f"\nIP 候选作品：{', '.join(ip_canon.title_guesses)}"
            f"\n标志性人名：{', '.join(ip_canon.canonical_names)}"
            f"\n著名事件：{', '.join(ip_canon.notable_events)}"
        )

    ip_pack_block = _build_ip_pack_block(ip_pack, fidelity_mode)

    return (
        f"世界描述：{description}\n"
        f"{ip_info}\n"
        f"角色名单：{', '.join(char_names)}\n"
        f"{ip_pack_block}"
        f"期望提取事件数：约 {k_target} 条（5-15 条，至少 3 条；有 IP 上下文时优先以 key_events 为锚点）\n\n"
        f"研究原文片段（格式：[passage_id] 原文）：\n{passage_lines}\n\n"
        "请提取 shared events，每条尽量注明 source_passage_ids（来自上方 passage id），无法对应时可留空。"
    )


def _build_supplement_prompt(
    description: str,
    ip_canon: IPCanon,
    characters: list[Character],
    existing_titles: list[str],
    need: int,
    *,
    ip_pack: IPKnowledgePack | None = None,
    fidelity_mode: FidelityMode = "none",
) -> str:
    """构建补充 shared events 的 user prompt（无 passage 依据）。"""
    char_names = [c.name for c in characters]
    ip_info = ""
    if ip_canon.title_guesses or ip_canon.canonical_names:
        ip_info = (
            f"\nIP 候选作品：{', '.join(ip_canon.title_guesses)}"
            f"\n标志性人名：{', '.join(ip_canon.canonical_names)}"
        )

    ip_pack_block = _build_ip_pack_block(ip_pack, fidelity_mode)

    return (
        f"世界描述：{description}\n"
        f"{ip_info}\n"
        f"角色名单：{', '.join(char_names)}\n"
        f"{ip_pack_block}"
        f"已有事件 title（不要重复）：{', '.join(existing_titles)}\n"
        f"还需补充 {need} 条 shared events，source_passage_ids 必须为 []。\n"
        "只输出 JSON。"
    )


def _parse_events_from_data(
    data: dict,
    valid_passage_ids: set[str],
    valid_npc_names: set[str],
) -> list[SharedEvent]:
    """从解析好的 dict 中提取 SharedEvent 列表，过滤非法 id 和 NPC 名。"""
    raw_events = data.get("events", [])
    if not isinstance(raw_events, list):
        return []

    result: list[SharedEvent] = []
    for item in raw_events:
        if not isinstance(item, dict):
            continue
        try:
            # 过滤 source_passage_ids 中不在输入列表里的
            raw_ids = item.get("source_passage_ids") or []
            filtered_ids = [pid for pid in raw_ids if pid in valid_passage_ids]

            # 过滤 involved_npcs 中不在角色名单里的
            raw_npcs = item.get("involved_npcs") or []
            filtered_npcs = [n for n in raw_npcs if n in valid_npc_names]

            # perceptions 解析（可选，宽松）
            raw_perceptions = item.get("perceptions") or {}
            perceptions: dict[str, SharedEventPerception] = {}
            if isinstance(raw_perceptions, dict):
                for npc_name, perc_data in raw_perceptions.items():
                    if npc_name in valid_npc_names and isinstance(perc_data, dict):
                        perceptions[npc_name] = SharedEventPerception(
                            knows=perc_data.get("knows", ""),
                            believes=perc_data.get("believes", ""),
                            feels=perc_data.get("feels", ""),
                        )

            event = SharedEvent(
                id=str(item.get("id", "")),
                title=str(item.get("title", "")),
                summary=str(item.get("summary", "")),
                era=str(item.get("era", "")),
                involved_npcs=filtered_npcs,
                perceptions=perceptions,
                source_passage_ids=filtered_ids,
            )
            result.append(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning("shared_event_parse_item_failed", error=str(exc), item=item)
            continue
    return result


def _dedup_by_title(events: list[SharedEvent]) -> list[SharedEvent]:
    """title 去重：同 title 取后者。"""
    seen: dict[str, SharedEvent] = {}
    for event in events:
        seen[event.title] = event
    return list(seen.values())


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


async def build_shared_events(
    description: str,
    ip_canon: IPCanon,
    characters: list[Character],
    passages: list[Passage],
    llm_router: Any,
    *,
    k_target: int = 15,
    k_min: int = 5,
    ip_pack: IPKnowledgePack | None = None,
    fidelity_mode: FidelityMode = "none",
) -> list[SharedEvent]:
    """从 ResearchPack.passages 提取共享历史事件列表。

    Args:
        description: 世界描述文字
        ip_canon: IP 结构化知识（probe_ip_canon 产出）
        characters: 角色列表（用于校验 involved_npcs）
        passages: 研究原文片段列表（source_passage_ids 的合法来源）
        llm_router: LLMRouter 实例
        k_target: 期望事件条数（LLM 参考，10-20 内自决）
        k_min: 最低条数；不足时强制补充
        ip_pack: 高复刻 IP 的结构化原作知识包（若有则注入到 prompt 作为锚点）
        fidelity_mode: "strict" / "loose" / "none"；只有前两者会真正注入 ip_pack 内容

    Returns:
        list[SharedEvent]，失败时返回空列表，不抛错。
    """
    valid_passage_ids: set[str] = {p.id for p in passages}
    valid_npc_names: set[str] = {c.name for c in characters}

    collected: list[SharedEvent] = []

    # -----------------------------------------------------------------------
    # 第一步：从 passages 提取
    # -----------------------------------------------------------------------
    try:
        user_prompt = _build_extract_prompt(
            description,
            ip_canon,
            characters,
            passages,
            k_target,
            ip_pack=ip_pack,
            fidelity_mode=fidelity_mode,
        )
        text = await _collect_stream_text(
            llm_router,
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=4096,
        )
        data = _extract_json_from_text(text)
        if data is None:
            logger.warning("shared_events_extract_json_failed", text_preview=text[:200])
            return []

        collected = _parse_events_from_data(data, valid_passage_ids, valid_npc_names)
        logger.info("shared_events_extracted", count=len(collected))

    except Exception as exc:  # noqa: BLE001
        logger.warning("shared_events_extract_failed", error=str(exc))
        return []

    # -----------------------------------------------------------------------
    # 第二步：如果条数 < k_min，补充
    # -----------------------------------------------------------------------
    if len(collected) < k_min:
        need = k_min - len(collected)
        existing_titles = [e.title for e in collected]
        try:
            supplement_prompt = _build_supplement_prompt(
                description,
                ip_canon,
                characters,
                existing_titles,
                need,
                ip_pack=ip_pack,
                fidelity_mode=fidelity_mode,
            )
            text2 = await _collect_stream_text(
                llm_router,
                system=_SUPPLEMENT_SYSTEM,
                messages=[{"role": "user", "content": supplement_prompt}],
                max_tokens=2048,
            )
            data2 = _extract_json_from_text(text2)
            if data2 is not None:
                # 补充的 events source_passage_ids 应为空（不校验，直接接受空列表）
                supplemented = _parse_events_from_data(
                    data2,
                    valid_passage_ids=set(),   # 空集合：不允许任何 passage id（过滤后均为 []）
                    valid_npc_names=valid_npc_names,
                )
                collected.extend(supplemented)
                logger.info("shared_events_supplemented", added=len(supplemented))
        except Exception as exc:  # noqa: BLE001
            logger.warning("shared_events_supplement_failed", error=str(exc))
            # 补充失败不影响已有结果

    # -----------------------------------------------------------------------
    # 第三步：title 去重
    # -----------------------------------------------------------------------
    result = _dedup_by_title(collected)
    logger.info("shared_events_final", count=len(result))
    return result
