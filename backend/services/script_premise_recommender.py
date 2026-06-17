"""grok 联网选题：给一个世界挑「最合适的下一个剧本」候选。

设计意图（见对话决策）：
- outline 为空 / 支撑不足时，借 grok 的联网能力，结合该世界的 canon
  (shared_events) + 已有剧本 (existing_scripts) 去重，挑出最该做的下一个剧本，
  再交给 DeepSeek 现有管线创作。
- grok 负责「选题 + canon 研究」，DeepSeek 负责「编剧」。
- 永不抛错：任何一步失败都退回更弱的兜底，最差返回 []（调用方退回空 outline，
  即原有行为），绝不阻断剧本创建。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from schemas.generation_strategy import ResearchRequest
from schemas.script_premise import ScriptPremise

logger = structlog.get_logger()

# 通用煽情套词黑名单——这些是「AI 腔」命名的重灾区，选题与最终命名都要避开。
BANNED_TITLE_WORDS = (
    "迷局", "觉醒", "抉择", "序章", "风云", "宿命", "终章", "黎明", "黄昏",
    "崛起", "陨落", "之影", "之殇", "纪元", "回响", "余烬", "序曲", "终焉",
)

_MAX_RESEARCH_QUERIES = 1
_MAX_SUMMARY_CHARS = 1800
# 外部 grok 调用硬上限——失败 / 慢时绝不能让选题挂住（曾观测到 401 重试风暴烧 6min）。
_GROK_RESEARCH_TIMEOUT_S = 70.0
_SYNTH_TIMEOUT_S = 60.0


async def _collect_text(provider: Any, *, system: str, content: str, max_tokens: int = 2048) -> str:
    parts: list[str] = []
    async for event in provider.stream_with_tools(
        messages=[{"role": "user", "content": content}],
        tools=[],
        system=system,
        max_tokens=max_tokens,
    ):
        if event.get("type") == "text_delta":
            parts.append(event.get("text", ""))
    return "".join(parts).strip()


def _extract_json(text: str) -> dict | None:
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


def _playable_names(world_data: dict) -> list[str]:
    names: list[str] = []
    for c in world_data.get("world_characters") or []:
        if isinstance(c, dict) and (c.get("playable") or c.get("is_image_target")) and c.get("name"):
            names.append(str(c["name"]))
    return names


def _existing_brief(world_data: dict) -> list[dict]:
    out: list[dict] = []
    for s in (world_data.get("existing_scripts") or [])[:8]:
        if not isinstance(s, dict):
            continue
        out.append(
            {
                "name": s.get("name", ""),
                "description": (s.get("description", "") or "")[:120],
                "event_names": list(s.get("event_names") or [])[:8],
            }
        )
    return out


def _shared_event_brief(world_data: dict) -> list[dict]:
    out: list[dict] = []
    for e in (world_data.get("shared_events") or [])[:20]:
        if not isinstance(e, dict):
            continue
        out.append(
            {
                "era": e.get("era", ""),
                "title": e.get("title", ""),
                "summary": (e.get("summary", "") or "")[:160],
            }
        )
    return out


async def _grok_research(world_data: dict, broker: Any) -> str:
    """用 grok web_search 拉原作主要剧情阶段 / 关键事件的联网研究摘要。"""
    if broker is None:
        return ""
    ip_name = world_data.get("name", "") or ""
    if not ip_name:
        return ""
    request = ResearchRequest(
        stage="script_premise",
        goal=f"{ip_name} 的主要剧情阶段、关键事件与故事线，用于规划互动剧本切入点",
        query_candidates=[
            f"{ip_name} 主要剧情线 关键事件 时间线",
            f"{ip_name} 故事阶段 重要桥段",
        ][:_MAX_RESEARCH_QUERIES],
    )
    try:
        ctx = await asyncio.wait_for(broker.research(request), timeout=_GROK_RESEARCH_TIMEOUT_S)
        return (ctx.summary or "")[:_MAX_SUMMARY_CHARS]
    except (Exception, asyncio.TimeoutError):  # noqa: BLE001
        logger.warning("script_premise_grok_research_failed", ip=ip_name, exc_info=True)
        return ""


def _build_synthesis_prompt(world_data: dict, research_summary: str, count: int) -> tuple[str, str]:
    playable = _playable_names(world_data)
    payload = {
        "world_name": world_data.get("name", ""),
        "era": world_data.get("era", ""),
        "genre": world_data.get("genre", ""),
        "base_setting": (world_data.get("base_setting", "") or "")[:600],
        "canon_events": _shared_event_brief(world_data),
        "existing_scripts": _existing_brief(world_data),
        "playable_characters": playable,
        "locations": [
            loc.get("name", "")
            for loc in (world_data.get("locations") or [])
            if isinstance(loc, dict) and loc.get("name")
        ],
        "web_research": research_summary,
    }
    system = (
        "你是资深互动剧本策划。结合原作 canon、联网研究、以及该世界「已有剧本」，"
        f"挑出最适合开发的下一个剧本，给出 {count} 个候选，按推荐度从高到低排序。\n"
        "硬约束：\n"
        "- 必须避开 existing_scripts 已覆盖的剧情弧 / 核心真相 / 主事件，挑没被做过的。\n"
        "- 若已有剧本为空，优先从原作较早 / 最具代表性的阶段切入。\n"
        "- povs 只能从 playable_characters 里选，1-3 个，名字必须完全一致。\n"
        "- entry_event 尽量锚定到 canon_events 或联网研究里的真实桥段。\n"
        "- 命名（title）贴原作语汇、用原作真实的地名 / 事件名 / 专有名词；"
        f"禁止使用这些通用煽情套词：{'、'.join(BANNED_TITLE_WORDS)}；不要堆砌"
        "「四字地名＋抽象词」的 AI 腔标题。\n"
        "- 各候选之间主题、视角、地点要尽量错开，不要互相重复。\n"
        "严格输出 JSON，不含任何解释文字：\n"
        '{"premises":[{"title":"","theme":"一句话主题","entry_event":"切入的原作事件",'
        '"povs":["可玩角色名"],"core_conflict":"核心冲突","ending_directions":"结局走向方向"}]}'
    )
    return system, json.dumps(payload, ensure_ascii=False)


def _parse_premises(data: dict | None, playable: list[str], count: int) -> list[ScriptPremise]:
    if not data:
        return []
    raw = data.get("premises")
    if not isinstance(raw, list):
        return []
    playable_set = set(playable)
    out: list[ScriptPremise] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        povs = [p for p in (item.get("povs") or []) if isinstance(p, str) and p in playable_set]
        premise = ScriptPremise(
            title=str(item.get("title") or "").strip(),
            theme=str(item.get("theme") or "").strip(),
            entry_event=str(item.get("entry_event") or "").strip(),
            povs=povs,
            core_conflict=str(item.get("core_conflict") or "").strip(),
            ending_directions=str(item.get("ending_directions") or "").strip(),
        )
        if premise.theme or premise.entry_event:
            out.append(premise)
        if len(out) >= count:
            break
    return out


def _deterministic_fallback(world_data: dict, count: int) -> list[ScriptPremise]:
    """grok / LLM 都失败时，从库里的 shared_events 里挑没被已有剧本覆盖的，
    拼最小可用 premise，保证调用方至少有东西可用。"""
    covered = " ".join(
        f"{s.get('name','')} {s.get('description','')} {' '.join(s.get('event_names') or [])}"
        for s in (world_data.get("existing_scripts") or [])
        if isinstance(s, dict)
    )
    playable = _playable_names(world_data)
    out: list[ScriptPremise] = []
    for e in world_data.get("shared_events") or []:
        if not isinstance(e, dict):
            continue
        title = str(e.get("title") or "").strip()
        summary = str(e.get("summary") or "").strip()
        if not title or (covered and title in covered):
            continue
        out.append(
            ScriptPremise(
                title=title,
                theme=summary[:80],
                entry_event=title,
                povs=playable[:2],
                core_conflict=summary,
                ending_directions="覆盖好 / 中 / 坏多种走向",
            )
        )
        if len(out) >= count:
            break
    return out


async def recommend_script_premises(
    *,
    world_data: dict,
    broker: Any = None,
    llm_router: Any = None,
    count: int = 4,
) -> list[ScriptPremise]:
    """返回 count 个「下一个剧本」候选，按推荐度排序。永不抛错。

    优先级：grok 联网研究 → grok synthesizer 合成候选 → DeepSeek(llm_router) 合成
    → shared_events 确定性兜底。
    """
    playable = _playable_names(world_data)
    research_summary = await _grok_research(world_data, broker)
    system, content = _build_synthesis_prompt(world_data, research_summary, count)

    # 合成候选：grok 的价值在「联网研究」那步；把研究 + canon 合成排序成候选是纯推理，
    # DeepSeek 又快又稳，作主力；grok synthesizer 仅作兜底。
    synth = getattr(broker, "synthesizer", None)
    for provider, tag in ((llm_router, "deepseek"), (synth, "grok_synth")):
        if provider is None:
            continue
        try:
            text = await asyncio.wait_for(
                _collect_text(provider, system=system, content=content, max_tokens=2048),
                timeout=_SYNTH_TIMEOUT_S,
            )
            premises = _parse_premises(_extract_json(text), playable, count)
            if premises:
                logger.info(
                    "script_premise_recommended",
                    via=tag,
                    count=len(premises),
                    had_research=bool(research_summary),
                )
                return premises
        except Exception:  # noqa: BLE001
            logger.warning("script_premise_synthesis_failed", via=tag, exc_info=True)

    fallback = _deterministic_fallback(world_data, count)
    logger.info("script_premise_fallback", count=len(fallback))
    return fallback
