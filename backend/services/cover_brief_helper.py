"""LLM-assisted derivation for ``CoverBrief`` fields that benefit from
context-sensitive judgment (English names, mood anchors, original-world
4-dim character descriptors).

Single LLM call per world (and per script). Outputs structured JSON. Cheap
enough to run on the most basic text slot — calling site passes whichever
LLMRouter it has (the agent's main router is currently used; a dedicated
``cover_brief_helper`` slot is registered in ``model_management`` but not
yet routed separately to keep changes minimal).

Failure mode: any parse error → empty-string fallbacks. ``cover_brief.py``
builders gracefully degrade (drop English subtitle, omit empty descriptor
fields). The pipeline never blocks on this helper.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from schemas.ip_knowledge_pack import IPKnowledgePack
from services.cover_brief import (
    IP_NAME_CONFIDENCE_FLOOR,
    CharacterCoverBrief,
    CoverBrief,
    EndingCoverBrief,
    derive_character_reference_anchor,
)
from services.ip_recognizer import IPRecognition

logger = structlog.get_logger()


_WORLD_HELPER_SYSTEM = """你给一个虚构故事世界的"封面图生成"提供文本辅助信息。

输入：world 元数据 + 需要画肖像的角色列表 + (可选) IP 识别结果。
输出：严格 JSON，仅一个对象，首字符 `{`，末字符 `}`，无解释文字。

输出 schema：
{
  "world_name_english": "世界名的英文/罗马字翻译（官方有英文名则用官方；否则拼音或意译，~3-6 词）",
  "mood": "3-5 个画面气质 cue 词，顿号分隔（如「毛笔书法、朱印、龙袍、烛火、深红」）",
  "characters": {
    "<原中文名>": {
      "name_english": "角色名英文/拼音（~2-4 词）",
      "mood_anchor": "4-8 字情绪/气质短语（'隐忍深沉' / '风尘仆仆' / '惊魂未定' 等）",
      "gender": "男 或 女 或 空字符串",
      "age_band": "少年/少女/青年/中年/老年 之一，或空字符串",
      "role_class": "职业或社会身份的短词（'武将' / '屠户' / '宰相' / '科学家' / '工人' / '钢琴少女' 等），或空字符串"
    }
  }
}

mood 规则（关键 — 决定封面是否撞均值）：
- 词的方向：视觉元素（毛笔书法 / 朱印 / 烛火 / 灯笼 / 星空 / 龙袍 / 案卷）、色调（深红 / 冷青 / 暮色 / 暖黄 / 暗银）、氛围（仙气 / 烟雾 / 留白 / 几何感 / 工业感）。
- 不要：人物动作、具体场景描述、物理摄影术语（"广角" / "浅景深" 等）。
- 不同世界 mood 必须有区分度——避免所有古装都"毛笔书法+朱印"撞均值。结合 world_name / IP / 故事核心冲突给出独特组合。

characters 规则：
- 当某角色是已知 IP 内的人物（输入会标注 `_has_ip_ref: true`），可以省略 gender/age_band/role_class（填空字符串）；mood_anchor 仍要填。
- 当角色不在 IP 中（`_has_ip_ref: false`），gender/age_band/role_class **必填**（不要留空），mood_anchor 也要填。
- mood_anchor 不要复用别人的关键词——同一世界里不同角色 mood 要有区分度。
- 不要复述 secret 内容；将隐藏特质转化为情绪姿态。
"""


_SCRIPT_HELPER_SYSTEM = """你给虚构剧本和它的结局们的"封面/卡片图生成"提供文本辅助信息。

输入：script 元数据 + endings 列表。
输出：严格 JSON：
{
  "script_title_english": "剧本名英文/拼音（~2-5 词）",
  "endings": {
    "<原结局标题>": {
      "title_english": "结局标题英文/意译（~2-5 词）"
    }
  }
}

首字符 `{`，末字符 `}`，无解释文字。
"""


def _extract_json(text: str) -> dict | None:
    """Best-effort JSON extraction tolerant to fences / stray prose."""
    if not text:
        return None
    for fence in ("```json", "```"):
        if fence in text:
            for chunk in text.split(fence)[1:]:
                body = chunk.split("```", 1)[0].strip()
                if body.startswith("{") and body.endswith("}"):
                    try:
                        parsed = json.loads(body)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        continue
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    if "{" in text and "}" in text:
        try:
            parsed = json.loads(text[text.find("{"): text.rfind("}") + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


async def _collect_text(llm: Any, *, system: str, user: str, max_tokens: int = 1024) -> str:
    parts: list[str] = []
    async for ev in llm.stream_with_tools(
        messages=[{"role": "user", "content": user}],
        tools=[],
        system=system,
        max_tokens=max_tokens,
    ):
        if ev.get("type") == "text_delta":
            parts.append(ev.get("text", ""))
    return "".join(parts).strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def derive_world_cover_brief(
    *,
    world_data: dict,
    characters: list[dict],
    recognition: IPRecognition | None,
    ip_pack: IPKnowledgePack | None,
    llm: Any,
) -> tuple[CoverBrief, dict[str, CharacterCoverBrief]]:
    """Produce the world ``CoverBrief`` + per-character ``CharacterCoverBrief`` map.

    Arguments:
      world_data: dict with at minimum ``name``, ``genre``, ``era``.
      characters: list of dicts with at minimum ``name``; optional fields
        ``role_tag``, ``personality``, ``gender``, ``is_image_target``.
        Only ``is_image_target`` characters get portraits.
      recognition: IP recognizer output; None for original worlds.
      ip_pack: IP knowledge pack; None when not known/hybrid.
      llm: LLMRouter or compatible — used for English names + descriptor extraction.

    Returns:
      (world_cover_brief, {character_name: character_cover_brief}).
      The character map only contains ``is_image_target`` characters.
    """
    world_name = (world_data.get("name") or "").strip()
    genre = (world_data.get("genre") or "").strip()
    era = (world_data.get("era") or "").strip()

    # V3: ip_name comes directly from the recognizer (no ip_mode three-way
    # branching). Below the confidence floor we drop the IP cue rather than
    # feed a low-confidence guess that misleads the visual DNA.
    ip_name: str | None = None
    if recognition is not None and recognition.kind != "original":
        rec_name = (recognition.ip_name or "").strip() or None
        if rec_name and recognition.confidence >= IP_NAME_CONFIDENCE_FLOOR:
            ip_name = rec_name

    target_chars = [c for c in characters if c.get("is_image_target")]

    # Precompute mechanical reference_anchors (no LLM needed)
    ref_map: dict[str, str | None] = {}
    for c in target_chars:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        ref_map[name] = derive_character_reference_anchor(
            character_name=name, ip_name=ip_name, ip_pack=ip_pack,
        )

    # Build LLM user message
    char_inputs = []
    for c in target_chars:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        char_inputs.append({
            "name": name,
            "role_tag": c.get("role_tag", ""),
            "personality": c.get("personality", ""),
            "gender_hint": c.get("gender", ""),
            "_has_ip_ref": ref_map.get(name) is not None,
        })

    user_payload = {
        "world": {
            "name": world_name,
            "genre": genre,
            "era": era,
            "description": world_data.get("description", "")[:300],
        },
        "ip_recognition": {
            "kind": recognition.kind if recognition else "original",
            "ip_name": ip_name or "",
        },
        "characters": char_inputs,
    }

    raw: dict | None = None
    try:
        text = await _collect_text(
            llm,
            system=_WORLD_HELPER_SYSTEM,
            user=json.dumps(user_payload, ensure_ascii=False),
            max_tokens=1024,
        )
        raw = _extract_json(text)
        if raw is None:
            logger.warning("cover_brief_helper_no_json", text_preview=text[:200])
    except Exception as exc:  # noqa: BLE001
        logger.warning("cover_brief_helper_failed", error=str(exc))

    raw = raw or {}
    world_name_english = (raw.get("world_name_english") or "").strip()
    mood = (raw.get("mood") or "").strip()
    char_helper = raw.get("characters") or {}
    if not isinstance(char_helper, dict):
        char_helper = {}

    # Build CoverBrief
    world_brief = CoverBrief(
        world_name=world_name,
        world_name_english=world_name_english,
        genre_tag=_genre_tag(genre, era),
        mood=mood,
        ip_name=ip_name,
        # essence drives ORIGINAL-world prompts (ignored for IP worlds). The
        # description is the model's window into what the world is about.
        essence=(world_data.get("description") or "").strip()[:300],
    )

    # Build per-character CharacterCoverBrief
    char_briefs: dict[str, CharacterCoverBrief] = {}
    for c in target_chars:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        helper_entry = char_helper.get(name) if isinstance(char_helper, dict) else None
        helper_entry = helper_entry if isinstance(helper_entry, dict) else {}
        char_briefs[name] = _build_character_brief(
            name=name,
            reference_anchor=ref_map.get(name),
            helper_entry=helper_entry,
            seed_gender=c.get("gender", ""),
        )

    return world_brief, char_briefs


def _genre_tag(genre: str, era: str) -> str:
    """Concatenate era + genre as a short tag for the prompt."""
    g = (genre or "").strip()
    e = (era or "").strip()
    if not g and not e:
        return ""
    if not e:
        return g
    if not g:
        return e
    # Avoid double-stuff if era is already in genre
    if e in g:
        return g
    return f"{e}{g}"


def _build_character_brief(
    *,
    name: str,
    reference_anchor: str | None,
    helper_entry: dict,
    seed_gender: str,
) -> CharacterCoverBrief:
    """Merge mechanical ref_anchor + helper LLM output + seed data into a brief."""
    name_english = (helper_entry.get("name_english") or "").strip()
    mood_anchor = (helper_entry.get("mood_anchor") or "").strip()

    if reference_anchor:
        # IP-pack character: 4-dim fallback fields stay empty
        return CharacterCoverBrief(
            name=name,
            name_english=name_english,
            reference_anchor=reference_anchor,
            mood_anchor=mood_anchor,
        )

    # Original / not-in-IP-pack character: 4-dim fallback required
    # Prefer seed_gender (admin-set in DB) over LLM-extracted gender
    gender_raw = (seed_gender or helper_entry.get("gender") or "").strip()
    gender: str = gender_raw if gender_raw in {"男", "女"} else ""
    age_band = (helper_entry.get("age_band") or "").strip()
    role_class = (helper_entry.get("role_class") or "").strip()
    return CharacterCoverBrief(
        name=name,
        name_english=name_english,
        gender=gender,  # type: ignore[arg-type]
        age_band=age_band,
        role_class=role_class,
        mood_anchor=mood_anchor,
    )


# ---------------------------------------------------------------------------
# Script helper
# ---------------------------------------------------------------------------


async def derive_script_cover_helpers(
    *,
    script_data: dict,
    endings: list[dict],
    llm: Any,
) -> tuple[str, dict[str, EndingCoverBrief]]:
    """Produce script_title_english + per-ending ``EndingCoverBrief``.

    Returns:
      (script_title_english, {ending_title: EndingCoverBrief}).
    """
    script_title = (script_data.get("name") or "").strip()
    user_payload = {
        "script": {
            "name": script_title,
            "description": (script_data.get("description") or "")[:300],
        },
        "endings": [
            {"title": (e.get("title") or "").strip()}
            for e in endings
            if (e.get("title") or "").strip()
        ],
    }

    raw: dict | None = None
    try:
        text = await _collect_text(
            llm,
            system=_SCRIPT_HELPER_SYSTEM,
            user=json.dumps(user_payload, ensure_ascii=False),
            max_tokens=512,
        )
        raw = _extract_json(text)
        if raw is None:
            logger.warning("cover_script_helper_no_json", text_preview=text[:200])
    except Exception as exc:  # noqa: BLE001
        logger.warning("cover_script_helper_failed", error=str(exc))

    raw = raw or {}
    script_title_english = (raw.get("script_title_english") or "").strip()
    endings_helper = raw.get("endings") or {}
    if not isinstance(endings_helper, dict):
        endings_helper = {}

    ending_briefs: dict[str, EndingCoverBrief] = {}
    for e in endings:
        title = (e.get("title") or "").strip()
        if not title:
            continue
        entry = endings_helper.get(title) if isinstance(endings_helper, dict) else None
        entry = entry if isinstance(entry, dict) else {}
        ending_briefs[title] = EndingCoverBrief(
            title=title,
            title_english=(entry.get("title_english") or "").strip(),
            description=(e.get("description") or "").strip(),
        )

    return script_title_english, ending_briefs


__all__ = [
    "derive_world_cover_brief",
    "derive_script_cover_helpers",
]
