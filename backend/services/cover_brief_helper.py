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
    GENRE_STYLE_POOL,
    IP_NAME_CONFIDENCE_FLOOR,
    CharacterCoverBrief,
    CoverBrief,
    EndingCoverBrief,
    derive_character_reference_anchor,
    pick_art_style,
)
from services.ip_recognizer import IPRecognition

logger = structlog.get_logger()


_WORLD_HELPER_SYSTEM = """你是 InkWild 的美术指导，给一个虚构故事世界的"封面图生成"提供文本辅助信息。

输入：world 元数据 + (可选) research_summary + 需要画肖像的角色列表 + (可选) IP 识别结果。
输出：严格 JSON，仅一个对象，首字符 `{`，末字符 `}`，无解释文字。

输出 schema：
{
  "world_name_english": "世界名的英文/罗马字翻译（官方有英文名则用官方；否则拼音或意译，~3-6 词）",
  "genre_category": "从给定题材大类里选一个最贴切的（只填大类名）",
  "cover_focus": "一句话：这个世界最独特、最勾人的主题与情绪钩子（给方向，不规定构图）",
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

genre_category 规则（用于决定封面画法，要选准）：
- 只能从这些大类里精确选一个填入：古风宫廷、武侠仙侠、赛博科幻、末世废土、悬疑推理、民国谍战、现代都市、校园日常、奇幻童话、恐怖诡秘、其他。
- 按世界的 name / genre / description / research_summary / IP 综合判断它最贴近哪个大类；拿不准就选最接近的，实在无法归类才用「其他」。
- 注意只判「题材大类」，不要判画法——具体画法由系统按大类自动分配。

cover_focus 规则（给封面定方向，关键）：
- 读懂这个世界后，提炼它最独特、最勾人的「主题 + 情绪钩子」——核心冲突 / 气质 / 最抓人的那个点，让人想点进去玩。
- 只给主题和钩子，**不要规定构图、人数、视角、姿势、具体摆位**——把「画成什么样」留给生图模型自己发挥思考。
- 一句话，必须独属于这个世界（避免放哪个世界都成立的泛话）。
- 如果有 research_summary，汲取它的**气质与核心冲突**凝成**一个**最抓人的情绪钩子——越精炼越好（≤20 字优先）；**不要罗列角色/道具/场景清单**（那是摆拍规格，违背"留给模型发挥"），也**不要复述 IP 已知的标志元素**：生图模型看到 IP 名就懂原作，钩子只补气质方向即可。
- 是已知 IP 就在钩子里点出 IP 名作锚（如「凡人修仙的冷峻隐忍与残酷攀升」），保持精炼；不要把 IP 泛化掉，也不要堆砌。审核/IP 风险由生图层兜底，不要自我阉割。

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
            "description": world_data.get("description", "")[:600],
            "research_summary": (world_data.get("research_summary") or "")[:800],
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
    mood = (raw.get("mood") or "").strip()  # V3 field, retained but not injected
    # art_style: the LLM classifies the world into a genre_category; the code
    # then deterministically picks a 画法 from that category's pool by hashing
    # the world name (spreads same-genre worlds across styles — see pick_art_style).
    genre_category = (raw.get("genre_category") or "").strip()
    if genre_category and genre_category not in GENRE_STYLE_POOL:
        logger.warning("cover_brief_genre_unknown", picked=genre_category, world=world_name)
    art_style = pick_art_style(genre_category, world_name)
    # cover_focus: the LLM-constructed 画面核心 (what to draw). Frees "画什么"
    # from the default single-人物 sameness. Empty → builders free-compose.
    cover_focus = (raw.get("cover_focus") or "").strip()
    char_helper = raw.get("characters") or {}
    if not isinstance(char_helper, dict):
        char_helper = {}

    # Build CoverBrief
    world_brief = CoverBrief(
        world_name=world_name,
        world_name_english=world_name_english,
        genre_tag=_genre_tag(genre, era),
        art_style=art_style,
        cover_focus=cover_focus,
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
