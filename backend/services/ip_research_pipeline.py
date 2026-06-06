"""IP Research Pipeline：多源抓取 → RAG 抽取 IPKnowledgePack → 4 维度完整性自检 → 补抓。

Phase 2.1 升级为 4 步流程：
1. Grok web_search 主搜索 → grok_summary + candidate_names
2. 多源并发深抓 → grok + 百度剧主页 + 百度角色页 (top N) + wiki + tavily fallback
3. RAG 抽取 IPKnowledgePack（context = grok 优先 + 百度细节）
4. 完整性自检 4 维度（characters/places/factions/key_events），≤ 2 轮补抓

前置：Stage 0 已识别出 IPRecognition (kind=known_ip 或 hybrid)。
fidelity_mode=none 时不应调用此 pipeline。
"""
import asyncio
import json
from typing import Any, TypeVar

import structlog
from pydantic import BaseModel

from schemas.ip_knowledge_pack import (
    IPKnowledgePack, IPCharacter, IPPlace, IPFaction, IPObject, IPEvent, FidelityMode,
    IPTimelineEntry,
)

_TModel = TypeVar("_TModel", bound=BaseModel)
from schemas.research_pack import Passage
from services.ip_pack_extractors.wikipedia import fetch_wikipedia
from services.ip_pack_extractors.tavily_site import fetch_via_tavily_site
from services.ip_pack_extractors.grok_search import fetch_via_grok_search
from services.ip_pack_extractors.baidu_baike import (
    fetch_baike_show, fetch_baike_characters_batch,
)
from services.ip_recognizer import IPRecognition

logger = structlog.get_logger()

MAX_PASSAGES = 30
MAX_PASSAGE_CHARS = 2000
MAX_BAIDU_CHARACTERS = 8
MAX_REFETCH_ROUNDS = 2  # Phase 2.1: 升级自 Phase 1 的 1 轮
MIN_PACK_CHARACTERS = 3  # quality gate: 抽不到 3 个就当 underfilled


class IPPackUnderfilledError(Exception):
    """raised when build_ip_knowledge_pack cannot produce a usable pack.

    Caught by the world creator agent's _run_ip_research; the agent emits an SSE
    warning so admin can decide to retry or downgrade fidelity_mode.
    """

    def __init__(self, ip_name: str, character_count: int, summary_len: int):
        self.ip_name = ip_name
        self.character_count = character_count
        self.summary_len = summary_len
        super().__init__(
            f"IP pack for {ip_name!r} underfilled: "
            f"characters={character_count} summary_len={summary_len}"
        )


_MISSING_CHECK_SYSTEM = """检查 IPKnowledgePack 完整性，列出 4 维度的遗漏。

输出 JSON:
{
  "missing_characters": ["名字1","名字2"],
  "missing_places": ["地点1"],
  "missing_factions": ["势力1"],
  "missing_key_events": ["事件1"]
}

某维度看着完整则对应数组返回 []。每个维度最多 5 个名字。只输出 JSON。"""


async def _collect_text(llm_router: Any, system: str, user: str, max_tokens: int = 4096) -> str:
    parts: list[str] = []
    async for ev in llm_router.stream_with_tools(
        messages=[{"role": "user", "content": user}],
        tools=[],
        system=system,
        max_tokens=max_tokens,
    ):
        if ev.get("type") == "text_delta":
            parts.append(ev.get("text", ""))
    return "".join(parts).strip()


def _extract_json(text: str) -> dict | None:
    candidates = [text]
    if "```json" in text:
        for part in text.split("```json")[1:]:
            candidates.append(part.split("```", 1)[0].strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"): text.rfind("}") + 1])
    for c in candidates:
        try:
            parsed = json.loads(c)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _passages_as_context_v2(passages: list[Passage]) -> str:
    """把 passages 拼成 LLM context，grok_search 优先，标注权威清单。"""
    grok = [p for p in passages if p.source == "grok_search"]
    baike = [p for p in passages if p.source == "baidu_baike"]
    other = [p for p in passages if p.source not in ("grok_search", "baidu_baike")]

    chunks: list[str] = []
    if grok:
        chunks.append("## Grok 综合搜索摘要（多源 cross-check 的权威清单）")
        for p in grok:
            chunks.append(f"[{p.id}] {p.text}")
    if baike:
        chunks.append("\n## 百度百科细节（角色 / 剧主页详细资料）")
        for p in baike:
            chunks.append(f"[{p.id}] {p.text}")
    if other:
        chunks.append("\n## 其他来源（wiki / 通用搜索）")
        for p in other:
            chunks.append(f"[{p.id}] ({p.source}) {p.text}")
    return "\n\n".join(chunks)


def _safe_build_list(
    cls: type[_TModel],
    items: Any,
    *,
    ip_name: str,
    field: str,
) -> list[_TModel]:
    """Build pydantic models from LLM JSON, dropping malformed entries.

    LLMs occasionally drift the schema (e.g. emit `description` instead of `event`
    in timeline). One bad entry used to raise ValidationError from a list
    comprehension and abort the entire pack construction; now bad entries are
    skipped with a warning so the rest of the pack survives.
    """
    out: list[_TModel] = []
    for item in items or []:
        if not isinstance(item, dict):
            logger.warning(
                "ip_pack_item_dropped",
                ip_name=ip_name, field=field, reason="not_a_dict",
            )
            continue
        try:
            out.append(cls(**item))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ip_pack_item_dropped",
                ip_name=ip_name, field=field, error=str(exc),
            )
    return out


def _empty_pack(rec: IPRecognition, fidelity_mode: FidelityMode) -> IPKnowledgePack:
    return IPKnowledgePack(
        ip_name=rec.ip_name or "",
        ip_type=rec.ip_type or "other",
        fidelity_mode=fidelity_mode,
        summary="", characters=[], places=[], factions=[],
        iconic_objects=[], key_events=[], tone_lingo=[],
        passages=[], timeline=[],
    )


async def _self_check_missing_v2(
    pack: IPKnowledgePack, llm_router: Any
) -> dict[str, list[str]]:
    empty = {
        "missing_characters": [],
        "missing_places": [],
        "missing_factions": [],
        "missing_key_events": [],
    }
    # Note: prior code shortcut returned empty when summary was blank; that
    # short-circuited the refetch loop precisely when extraction failed worst.
    # Now we always ask the missing-check LLM — it can use the current pack's
    # character names + ip_name to suggest missing entries even with no summary.

    user = (
        f"summary：{pack.summary}\n\n"
        f"已有 characters: {', '.join(c.name for c in pack.characters)}\n"
        f"已有 places: {', '.join(p.name for p in pack.places)}\n"
        f"已有 factions: {', '.join(f.name for f in pack.factions)}\n"
        f"已有 key_events: {', '.join(e.name for e in pack.key_events)}"
    )
    try:
        text = await _collect_text(llm_router, _MISSING_CHECK_SYSTEM, user, max_tokens=512)
        data = _extract_json(text) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("self_check_v2_failed", error=str(exc))
        return empty

    def _clean(key: str) -> list[str]:
        return [n for n in (data.get(key) or []) if isinstance(n, str)][:5]

    return {
        "missing_characters": _clean("missing_characters"),
        "missing_places": _clean("missing_places"),
        "missing_factions": _clean("missing_factions"),
        "missing_key_events": _clean("missing_key_events"),
    }


_PRE_EXTRACT_SYSTEM = """你是 IP 知识抽取助手。给你一个已知作品名（影视剧/小说/游戏/动漫），
请凭你的训练知识，列出该作品的核心结构化信息。

输出严格 JSON：
{
  "summary": "200~400 字的剧情概述",
  "characters": [
    {"name":"姓名","role_in_story":"角色定位","relation_to_protagonist":"与主角关系","traits":["性格1","性格2"],"must_have":true/false,"voice_style":"台词口吻30字","story_arc":"成长弧线30~80字"}
  ],
  "places": [{"name":"地点","description":"30字简介","must_have":true/false,"faction_owner":"所属势力"}],
  "factions": [{"name":"势力","description":"30字简介"}],
  "iconic_objects": [{"name":"标志物","description":"30字简介"}],
  "key_events": [{"name":"事件","description":"30字简介"}],
  "timeline": [{"when":"序幕/中段/结局","event":"30~60字"}],
  "tone_lingo": ["原作风格鲜明的称谓 / 口头禅"]
}

要求：
1. characters 至少 8 个，包含核心主角 / 反派 / 配角；男女主和首要反派标 must_have=true（3~5 个），其余 must_have=false。
2. places ≥ 5，factions ≥ 3，key_events ≥ 5，timeline ≥ 3。
3. **不需要填 source_passage_ids**（下游会做事实核查再补）。
4. 如果你不熟悉这个作品，宁可少给也不要瞎编 —— 把 characters/places 等数组留空，summary 也留空，下游会走兜底。
5. 严格 JSON，无解释文字。"""


_GROUND_SYSTEM = """你是 IP 知识包事实核查助手。

输入：
- 一个候选 IPKnowledgePack（含 characters/places/factions/...）凭训练知识生成
- 一组从权威源（百度百科/维基/豆瓣/Grok 搜索）抓的 passages

任务：基于 passages **验证、补 source_passage_ids、补遗漏、删 passages 明确矛盾**。

具体规则：
1. **保留**候选里在 passages 中出现的项 —— 给它填 source_passage_ids（passage id 列表）。
2. **保留**候选里**未在 passages 中出现但你认为是正典**的项（passages 经常覆盖不全），source_passage_ids 留空数组即可，**不要删**。
3. **删除**候选里**与 passages 明确矛盾**的项（比如名字写错、派系明显不对）。
4. **新增** passages 中提到但候选漏掉的核心角色 / 地点 / 势力 / 事件。
5. 更新 summary 让它更贴近 passages 的事实描述（保留候选里没有的细节）。

输出严格 JSON（schema 与候选完全相同）：
{
  "summary": "...",
  "characters": [{"name":"","role_in_story":"","relation_to_protagonist":"","traits":[],"must_have":true,"source_passage_ids":[]}],
  "places": [{"name":"","description":"","must_have":true,"source_passage_ids":[],"faction_owner":""}],
  "factions": [...], "iconic_objects": [...], "key_events": [...],
  "timeline": [{"when":"","event":"","source_passage_ids":[]}],
  "tone_lingo": []
}

严格 JSON，无解释文字。"""


async def _pre_extract_canon(
    rec: IPRecognition, llm_router: Any
) -> IPKnowledgePack:
    """Stage 1: 凭主 LLM 训练知识列候选 pack（不喂 passages）。

    冷门 IP 模型不熟悉时返回空数组，由调用方判断 fallback。
    """
    user = f"IP 名：{rec.ip_name}\nIP 类型：{rec.ip_type or 'other'}"
    try:
        text = await _collect_text(llm_router, _PRE_EXTRACT_SYSTEM, user, max_tokens=4096)
        data = _extract_json(text) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("ip_pre_extract_failed", ip_name=rec.ip_name, error=str(exc))
        data = {}

    ip_name = rec.ip_name or ""
    return IPKnowledgePack(
        ip_name=ip_name,
        ip_type=rec.ip_type or "other",
        fidelity_mode="none",  # placeholder; set on final pack
        summary=data.get("summary", ""),
        characters=_safe_build_list(IPCharacter, data.get("characters"), ip_name=ip_name, field="characters"),
        places=_safe_build_list(IPPlace, data.get("places"), ip_name=ip_name, field="places"),
        factions=_safe_build_list(IPFaction, data.get("factions"), ip_name=ip_name, field="factions"),
        iconic_objects=_safe_build_list(IPObject, data.get("iconic_objects"), ip_name=ip_name, field="iconic_objects"),
        key_events=_safe_build_list(IPEvent, data.get("key_events"), ip_name=ip_name, field="key_events"),
        tone_lingo=list(data.get("tone_lingo") or []),
        timeline=_safe_build_list(IPTimelineEntry, data.get("timeline"), ip_name=ip_name, field="timeline"),
        passages=[],
    )


async def _ground_and_augment(
    rec: IPRecognition,
    candidates: IPKnowledgePack,
    passages: list[Passage],
    fidelity_mode: FidelityMode,
    llm_router: Any,
) -> IPKnowledgePack:
    """Stage 3: 第二轮 LLM —— 用 passages 验证 / 补 source_passage_ids / 增删。"""
    candidate_json = json.dumps(
        {
            "summary": candidates.summary,
            "characters": [c.model_dump() for c in candidates.characters],
            "places": [p.model_dump() for p in candidates.places],
            "factions": [f.model_dump() for f in candidates.factions],
            "iconic_objects": [o.model_dump() for o in candidates.iconic_objects],
            "key_events": [e.model_dump() for e in candidates.key_events],
            "timeline": [t.model_dump() for t in candidates.timeline],
            "tone_lingo": candidates.tone_lingo,
        },
        ensure_ascii=False,
    )
    user = (
        f"# IP\n名：{rec.ip_name}\n类型：{rec.ip_type or 'other'}\n\n"
        f"# 候选（凭训练知识生成，待核查）\n{candidate_json}\n\n"
        f"# 权威 passages\n{_passages_as_context_v2(passages)}"
    )

    try:
        text = await _collect_text(llm_router, _GROUND_SYSTEM, user, max_tokens=8192)
        data = _extract_json(text) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("ip_ground_failed", ip_name=rec.ip_name, error=str(exc))
        # fallback: 候选 pack 原样返回 + 把 passages 挂上
        pack = candidates
        pack.fidelity_mode = fidelity_mode
        pack.passages = passages
        return pack

    ip_name = rec.ip_name or ""
    return IPKnowledgePack(
        ip_name=ip_name,
        ip_type=rec.ip_type or "other",
        fidelity_mode=fidelity_mode,
        summary=data.get("summary", "") or candidates.summary,
        characters=_safe_build_list(IPCharacter, data.get("characters"), ip_name=ip_name, field="characters"),
        places=_safe_build_list(IPPlace, data.get("places"), ip_name=ip_name, field="places"),
        factions=_safe_build_list(IPFaction, data.get("factions"), ip_name=ip_name, field="factions"),
        iconic_objects=_safe_build_list(IPObject, data.get("iconic_objects"), ip_name=ip_name, field="iconic_objects"),
        key_events=_safe_build_list(IPEvent, data.get("key_events"), ip_name=ip_name, field="key_events"),
        tone_lingo=list(data.get("tone_lingo") or candidates.tone_lingo or []),
        timeline=_safe_build_list(IPTimelineEntry, data.get("timeline"), ip_name=ip_name, field="timeline"),
        passages=passages,
    )


async def build_ip_knowledge_pack(
    rec: IPRecognition,
    fidelity_mode: FidelityMode,
    llm_router: Any,
    tavily: Any,
    grok_provider: Any | None = None,
) -> IPKnowledgePack:
    """主入口（RAG-first，2026-05 重写）。

    流程：
        Stage 1  _pre_extract_canon          (no passages, 主 LLM 凭训练知识)
        Stage 2  _gather_passages_v3         (grok web_search + baike + wiki + tavily)
        Stage 3  _ground_and_augment         (passages 核查 + 补 source_passage_ids + 增删)
        Stage 4  self-check + refetch loop   (最多 MAX_REFETCH_ROUNDS 轮补抓)
        Stage 5  quality gate                (characters < MIN_PACK_CHARACTERS → 抛 IPPackUnderfilledError)

    冷门 IP 主 LLM 不熟悉 → Stage 1 给空 / 单薄。Stage 2/3 仍照常跑（retrieve-first 兜底）。
    Stage 5 仍能跑出 ≥ MIN_PACK_CHARACTERS 才算成功；否则抛异常让上层 emit warning。
    """
    if rec.kind not in ("known_ip", "hybrid") or not rec.ip_name:
        return _empty_pack(rec, fidelity_mode)

    # === Stage 1: pre-extract canon (RAG-first) ===
    candidates_pack = await _pre_extract_canon(rec, llm_router)
    pre_names = [c.name for c in candidates_pack.characters[:MAX_BAIDU_CHARACTERS]]
    logger.info(
        "ip_pre_extract_done",
        ip_name=rec.ip_name,
        characters=len(candidates_pack.characters),
        places=len(candidates_pack.places),
        factions=len(candidates_pack.factions),
        summary_len=len(candidates_pack.summary),
    )

    # === Stage 2: gather passages (RAG candidate names drive baike fetching) ===
    passages, _ = await _gather_passages_v3(
        rec, tavily, grok_provider, prefer_candidates=pre_names,
    )

    # === Stage 3: ground & augment ===
    if not passages:
        # No external corpus — return pre-extract pack as best effort with warning.
        logger.warning("ip_research_no_passages", ip_name=rec.ip_name)
        pack = candidates_pack
        pack.fidelity_mode = fidelity_mode
        pack.passages = []
    else:
        pack = await _ground_and_augment(
            rec, candidates_pack, passages, fidelity_mode, llm_router,
        )

    # === Stage 4: self-check + refetch loop ===
    for _ in range(MAX_REFETCH_ROUNDS):
        missing = await _self_check_missing_v2(pack, llm_router)
        missing_chars = missing["missing_characters"]
        missing_places = missing["missing_places"]
        if not missing_chars and not missing_places:
            break

        extra_passages: list[Passage] = []
        if missing_chars:
            chars_extra = await fetch_baike_characters_batch(
                missing_chars, max_chars=MAX_PASSAGE_CHARS, concurrency=4,
            )
            extra_passages.extend(chars_extra)
        if missing_places:
            for place_name in missing_places:
                place_passages = await fetch_via_tavily_site(
                    place_name, rec.ip_type or "other", tavily, max_per_site=1,
                )
                extra_passages.extend(place_passages)

        if not extra_passages:
            break

        passages = (passages + extra_passages)[:MAX_PASSAGES]
        pack = await _ground_and_augment(rec, pack, passages, fidelity_mode, llm_router)

    # === Stage 5: quality gate ===
    if len(pack.characters) < MIN_PACK_CHARACTERS:
        raise IPPackUnderfilledError(
            ip_name=rec.ip_name,
            character_count=len(pack.characters),
            summary_len=len(pack.summary),
        )

    logger.info(
        "ip_research_done",
        ip_name=rec.ip_name,
        characters=len(pack.characters),
        must_have=len(pack.must_have_character_names()),
        places=len(pack.places),
        factions=len(pack.factions),
        passages=len(pack.passages),
    )
    return pack


async def _gather_passages_v3(
    rec: IPRecognition,
    tavily: Any,
    grok_provider: Any | None,
    *,
    prefer_candidates: list[str] | None = None,
) -> tuple[list[Passage], list[str]]:
    """4 步多源抓取（v3：候选名优先来自 RAG-first 阶段，Grok 退化为补充源）。

    Step 1: Grok 主搜索（拿额外候选名 + 一段权威总结）
    Step 2: 用 prefer_candidates ∪ grok candidates 去抓百度角色页
    Step 3: 并发 baike_show + wiki + tavily_site
    """
    ip_name = rec.ip_name or ""
    ip_type = rec.ip_type or "other"
    if not ip_name:
        return [], []

    grok_passages, grok_candidates = await fetch_via_grok_search(ip_name, ip_type, grok_provider)

    # union candidates: pre-extract 优先，grok 补
    union: list[str] = []
    seen: set[str] = set()
    for n in list(prefer_candidates or []) + grok_candidates:
        n = (n or "").strip()
        if n and n not in seen:
            seen.add(n)
            union.append(n)
    top_candidates = union[:MAX_BAIDU_CHARACTERS]

    async def _baidu_chars() -> list[Passage]:
        if not top_candidates:
            return []
        return await fetch_baike_characters_batch(
            top_candidates, max_chars=MAX_PASSAGE_CHARS, concurrency=4,
        )

    results = await asyncio.gather(
        fetch_baike_show(ip_name, max_chars=MAX_PASSAGE_CHARS),
        _baidu_chars(),
        fetch_wikipedia(ip_name, max_chars=MAX_PASSAGE_CHARS),
        fetch_via_tavily_site(ip_name, ip_type, tavily, max_chars=MAX_PASSAGE_CHARS),
        return_exceptions=True,
    )
    baike_show, baike_chars, wiki, site = [
        r if not isinstance(r, BaseException) else [] for r in results
    ]
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            logger.warning("ip_gather_source_failed", index=i, error=str(r))

    all_passages: list[Passage] = []
    all_passages.extend(grok_passages)
    all_passages.extend(list(baike_show))
    all_passages.extend(list(baike_chars))
    all_passages.extend(list(wiki))
    all_passages.extend(list(site))
    return all_passages[:MAX_PASSAGES], union
