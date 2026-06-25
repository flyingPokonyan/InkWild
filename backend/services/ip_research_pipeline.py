"""IP Research Pipeline：grok 多角度并行研究 → 按轴抽取 merge → 接地核查 → 自检补抓。

流程（2026-06-22 重写，C 阶段）：
1. per-axis pre-extract：4 个聚焦轴（核心 / 对立 / 外围 NPC / 设定）并发凭训练知识抽取 → merge
2. grok fan-out：同 4 轴并发 web_search → 富 passages + 候选名并集（**生产唯一活源**）
3. ground & augment：用 passages 核查 / 补 / 增删（单次，验证非生成）
4. 完整性自检 + grok 补抓（≤ 2 轮）
5. quality gate：characters < 按 IP 规模缩放的下限 → IPPackUnderfilledError

校正（2026-06-22）：百度 / wiki / tavily 在生产是死源（403 / 无 key / 抓不到），已退役，
不再空转。grok 是唯一活源，因此把它做成多角度并行 + 抽取目标按题材规模放开（替掉旧"至少 8"
一刀切），专门解决"单 query 只捞到最有名几个 → 世界从源头就薄"。

前置：Stage 0 已识别出 IPRecognition (kind=known_ip 或 hybrid)。fidelity_mode=none 时不调用。
"""
import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog
from pydantic import BaseModel

from schemas.ip_knowledge_pack import (
    IPKnowledgePack, IPCharacter, IPPlace, IPFaction, IPObject, IPEvent, FidelityMode,
    IPTimelineEntry,
)

_TModel = TypeVar("_TModel", bound=BaseModel)
from schemas.research_pack import Passage
from services.ip_pack_extractors.grok_search import fetch_via_grok_search
from services.ip_recognizer import IPRecognition

logger = structlog.get_logger()

MAX_PASSAGES = 40
MAX_PASSAGE_CHARS = 2000
# 自检补抓轮数。每轮 = 1 次 grok + 重新 ground 整个 pack（~100s），是 IP 抽取最大的墙钟
# 开销。2→1：must_have 已由下游 roster `_ensure_must_have` + critic `_backfill` 确定性兜底，
# 研究层不必再补抓两轮，一轮足够捞回常见遗漏，省约 100s。
MAX_REFETCH_ROUNDS = 1

# ── 多角度 fan-out 轴（C1/C2）────────────────────────────────────────────────
# 固定 4 类 coverage role 保证 merge 稳定；grok query 措辞 + pre-extract 聚焦提示按轴定。
# 题材无关（按"故事功能"切分，非"主角/反派"字面）——推理无明面反派、武侠是门派、群像无单
# 主角时也成立。原创世界（kind != known_ip/hybrid）整条 pipeline 跳过。
# (axis_key, grok_focus, preextract_focus_hint)
_RESEARCH_AXES: list[tuple[str, str, str]] = [
    ("core", "主要角色 核心人物 主角",
     "本作核心 / 中心人物（主角一方）"),
    ("opposing", "反派 对手 对立势力 竞争者 嫌疑人",
     "与主角对立 / 竞争 / 制造冲突的人物（反派 / 对手 / 嫌疑人 / 敌对势力）"),
    ("supporting", "配角 次要角色 全部登场人物 龙套 工具人",
     "外围配角与功能性角色——尽量穷举次要人物，别只给最有名的几个"),
    ("world", "世界观 设定 地点 势力 组织 重要事件 规矩",
     "世界设定：地点 / 势力 / 重要事件 / 规矩黑话"),
]


def _target_characters(ip_type: str) -> int:
    """按题材规模给目标角色数（替掉旧'至少 8'一刀切）。长篇剧/小说取大。"""
    return {
        "tv": 26, "novel": 26, "anime": 22, "game": 22,
        "movie": 15, "other": 15,
    }.get(ip_type or "other", 15)


def _min_pack_characters(ip_type: str) -> int:
    """quality gate 下限：低于此当 underfilled。按规模抬高，避免'抽到 3 个就放行'。"""
    return max(5, _target_characters(ip_type) // 4)


def _norm_name(name: str) -> str:
    """规范化人名用于 merge 去重：去空白与中点。"""
    return re.sub(r"[\s·•・]", "", str(name or "")).strip()


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


async def _collect_text(
    llm_router: Any, system: str, user: str, max_tokens: int = 4096,
    *, reasoning: bool | None = None,
) -> str:
    # 规划/抽取类步骤（pre-extract / self-check）传 reasoning=True 重新打开 CoT；
    # _ground（8192 大输出，截断风险）保持默认关。只在显式设置时透传，兼容旧 fakes。
    extra: dict = {"reasoning": reasoning} if reasoning is not None else {}
    parts: list[str] = []
    async for ev in llm_router.stream_with_tools(
        messages=[{"role": "user", "content": user}],
        tools=[],
        system=system,
        max_tokens=max_tokens,
        **extra,
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


def _coerce_str_list(items: Any) -> list[str]:
    """tone_lingo 等 list[str] 字段抗 LLM 漂移：dict 取 term/name/word，否则 str()。

    实测 ground 阶段 LLM 把 tone_lingo 写成 [{"term":"一丈红",...}] → 直接进
    IPKnowledgePack(list[str]) 会 ValidationError 炸掉整个 build。这里统一压成字符串。
    """
    out: list[str] = []
    for it in items or []:
        if isinstance(it, str):
            s = it.strip()
        elif isinstance(it, dict):
            s = str(it.get("term") or it.get("name") or it.get("word") or "").strip()
        else:
            s = str(it).strip()
        if s:
            out.append(s)
    return out


def _prep_char_dicts(items: Any) -> list[Any]:
    """角色 dict 抗漂移：补 must_have 默认值，避免漏填一个 bool 就被整条丢掉。

    实测 LLM 偶尔漏 must_have（IPCharacter 里它是 required）→ _safe_build_list 丢掉整个
    角色（如温实初）→ 平白损失厚度。这里给缺失的必填项兜个默认。
    """
    out: list[Any] = []
    for it in items or []:
        if isinstance(it, dict):
            it.setdefault("must_have", False)
            it.setdefault("relation_to_protagonist", "")
            it.setdefault("role_in_story", "")
        out.append(it)
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
        # 不开 reasoning：输出小但 max_tokens=512 极小，开 CoT 必截断（见 _pre_extract 注）。
        text = await _collect_text(
            llm_router, _MISSING_CHECK_SYSTEM, user, max_tokens=512,
        )
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
1. characters 尽量收全（参考下方给的目标数量），包含核心主角 / 反派 / 配角 / 次要人物 / 功能性 NPC；
   **别只给最有名的几个**——撑起世界靠的是有名有姓的配角群。
   must_have：**只标剧情离不开、必须在场的最核心 5-8 个**（男女主 + 首要反派），其余一律 false。
   must_have 不是"重要 / 出彩"的意思——配角再精彩、戏份再多，只要剧情没他也能成立，就设 false。
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
6. **must_have 纪律**：只有剧情离不开、必须在场的最核心 5-8 个角色（男女主 + 首要反派）才标 must_have=true，
   其余一律 false。配角再精彩也设 false；**绝不要把保留下来的角色都标 must_have**。

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
    rec: IPRecognition,
    llm_router: Any,
    *,
    focus_hint: str = "",
    target_chars: int = 8,
) -> IPKnowledgePack:
    """Stage 1: 凭主 LLM 训练知识列候选 pack（不喂 passages）。

    ``focus_hint`` 为多角度 fan-out 的某一轴——告诉模型这次重点挖哪一片，多轴并发后
    merge，比单次"一把抓"更不容易停在最有名的几个。``target_chars`` 把目标数量写进
    user content（按题材规模缩放）。

    注：本步**不开 reasoning**——它输出大块 JSON，开 CoT 会让隐藏推理吃掉 token 预算、
    正文 JSON 被截断成空（2026-06-22 e2e 实测：reasoning+4096 → 0 角色）。厚度靠 4 轴
    fan-out + 目标数缩放，不靠 CoT。约束满足类的 roster 才开 reasoning（输出小、风险低）。

    冷门 IP 模型不熟悉时返回空数组，由调用方判断 fallback。
    """
    focus_line = (
        f"\n本次重点挖掘：{focus_hint}（这一片尽量挖全、穷举；其他维度可顺带给）"
        if focus_hint else ""
    )
    user = (
        f"IP 名：{rec.ip_name}\nIP 类型：{rec.ip_type or 'other'}\n"
        f"目标：characters 力求 {target_chars} 个以上，尽量收全有名有姓的角色{focus_line}"
    )
    try:
        text = await _collect_text(
            llm_router, _PRE_EXTRACT_SYSTEM, user, max_tokens=4096,
        )
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
        characters=_safe_build_list(IPCharacter, _prep_char_dicts(data.get("characters")), ip_name=ip_name, field="characters"),
        places=_safe_build_list(IPPlace, data.get("places"), ip_name=ip_name, field="places"),
        factions=_safe_build_list(IPFaction, data.get("factions"), ip_name=ip_name, field="factions"),
        iconic_objects=_safe_build_list(IPObject, data.get("iconic_objects"), ip_name=ip_name, field="iconic_objects"),
        key_events=_safe_build_list(IPEvent, data.get("key_events"), ip_name=ip_name, field="key_events"),
        tone_lingo=_coerce_str_list(data.get("tone_lingo")),
        timeline=_safe_build_list(IPTimelineEntry, data.get("timeline"), ip_name=ip_name, field="timeline"),
        passages=[],
    )


async def _ground_and_augment(
    rec: IPRecognition,
    candidates: IPKnowledgePack,
    passages: list[Passage],
    fidelity_mode: FidelityMode,
    llm_router: Any,
    *,
    target_chars: int = 8,
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
        f"# IP\n名：{rec.ip_name}\n类型：{rec.ip_type or 'other'}\n"
        f"目标：characters 力求 {target_chars} 个以上，passages 里出现的有名有姓角色尽量都收进来\n\n"
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
    grounded_chars = _safe_build_list(
        IPCharacter, _prep_char_dicts(data.get("characters")), ip_name=ip_name, field="characters"
    )
    # 安全网：ground 这步是"核查/增删"，绝不该把整份候选名册清空。但 OpenCode 的
    # deepseek-v4-pro 等"reasoning 关不掉"的模型偶发把思考吃满 token、正文 characters 截成
    # 空数组（仍是合法 JSON，逃过上面的 except 兜底）→ 36 个角色瞬间归零 → 下游 underfill
    # → 整个 IP 复刻降级成空 pack。这里兜底：grounded 角色为空但候选非空时，保留候选名册。
    if not grounded_chars and candidates.characters:
        logger.warning(
            "ip_ground_emptied_characters_kept_candidates",
            ip_name=ip_name, candidate_count=len(candidates.characters),
        )
        grounded_chars = candidates.characters
    return IPKnowledgePack(
        ip_name=ip_name,
        ip_type=rec.ip_type or "other",
        fidelity_mode=fidelity_mode,
        summary=data.get("summary", "") or candidates.summary,
        characters=grounded_chars,
        places=_safe_build_list(IPPlace, data.get("places"), ip_name=ip_name, field="places"),
        factions=_safe_build_list(IPFaction, data.get("factions"), ip_name=ip_name, field="factions"),
        iconic_objects=_safe_build_list(IPObject, data.get("iconic_objects"), ip_name=ip_name, field="iconic_objects"),
        key_events=_safe_build_list(IPEvent, data.get("key_events"), ip_name=ip_name, field="key_events"),
        tone_lingo=_coerce_str_list(data.get("tone_lingo")) or candidates.tone_lingo,
        timeline=_safe_build_list(IPTimelineEntry, data.get("timeline"), ip_name=ip_name, field="timeline"),
        passages=passages,
    )


def _char_info_len(c: IPCharacter) -> int:
    """角色信息量（merge 去重时取信息最全的那条）。"""
    return (
        len("".join(c.traits or []))
        + len(c.role_in_story or "")
        + len(c.story_arc or "")
        + len(c.voice_style or "")
    )


def _merge_packs(
    packs: list[IPKnowledgePack], rec: IPRecognition, fidelity_mode: FidelityMode,
) -> IPKnowledgePack:
    """实体级 merge 多个 per-axis pack（C2）。

    characters：按 _norm_name 并集去重，同名取信息最全的记录，must_have = OR 合并
    （任一轴标了 must_have 即 must_have）。places / factions / objects / events / timeline：
    按 name 并集去重。summary 取最长。tone_lingo 并集。
    """
    ip_name = rec.ip_name or ""

    # characters：richer + must_have OR
    char_by: dict[str, IPCharacter] = {}
    for p in packs:
        for c in p.characters:
            k = _norm_name(c.name)
            if not k:
                continue
            cur = char_by.get(k)
            if cur is None:
                char_by[k] = c
            else:
                richer = c if _char_info_len(c) > _char_info_len(cur) else cur
                char_by[k] = richer.model_copy(
                    update={"must_have": cur.must_have or c.must_have}
                )

    def _union_by_name(getter) -> list:
        seen: set[str] = set()
        out: list = []
        for p in packs:
            for item in getter(p):
                k = _norm_name(getattr(item, "name", ""))
                if not k or k in seen:
                    continue
                seen.add(k)
                out.append(item)
        return out

    summary = max((p.summary for p in packs), key=len, default="")
    tone: list[str] = []
    seen_tone: set[str] = set()
    for p in packs:
        for t in p.tone_lingo or []:
            if t not in seen_tone:
                seen_tone.add(t)
                tone.append(t)
    # timeline 无 name 字段，按 (when,event) 去重
    tl_seen: set[tuple] = set()
    timeline: list[IPTimelineEntry] = []
    for p in packs:
        for t in p.timeline or []:
            key = (getattr(t, "when", ""), getattr(t, "event", ""))
            if key not in tl_seen:
                tl_seen.add(key)
                timeline.append(t)

    return IPKnowledgePack(
        ip_name=ip_name,
        ip_type=rec.ip_type or "other",
        fidelity_mode=fidelity_mode,
        summary=summary,
        characters=list(char_by.values()),
        places=_union_by_name(lambda p: p.places),
        factions=_union_by_name(lambda p: p.factions),
        iconic_objects=_union_by_name(lambda p: p.iconic_objects),
        key_events=_union_by_name(lambda p: p.key_events),
        tone_lingo=tone,
        timeline=timeline,
        passages=[],
    )


_CONSOLIDATE_SYSTEM = """你是角色去重助手。给你同一作品的一批角色名，其中有些是同一个人的不同
称呼（本名 / 封号 / 全名 / 带括注 / 别名），把指代同一人的归为一组。

输出严格 JSON：
{"groups":[{"canonical":"最完整最正式的原作名","aliases":["该人的所有其他写法（含 canonical 本身）"]}]}

规则：
- canonical 取信息最全、最正式的原作名（如有封号+本名，用最常用的全称）。
- **只合并确实是同一人**的不同写法（如"华妃"/"年世兰"/"华妃（年世兰）"是同一人；
  "雍正"/"爱新觉罗·胤禛"/"皇帝（雍正）"是同一人）。不同的人（如端妃 vs 敬妃）**绝不合并**。
- 输入里每个名字都必须出现在某一组的 aliases 里（哪怕独自成组）。
- 只输出 JSON，无解释文字。"""


async def _consolidate_characters(
    chars: list[IPCharacter], rec: IPRecognition, llm_router: Any,
) -> list[IPCharacter]:
    """LLM 归并同一角色的名称变体（fan-out 多轴并发的副作用）。

    4 路并发各自给同一人不同叫法（华妃/年世兰/华妃（年世兰）），_norm_name 认不出
    "胤禛=雍正"这类需要知识的等价 → 同一角色在 roster 出现多次。这里用一次 LLM
    调用拿到别名分组，按规范名合并：取信息最全记录，must_have = OR。失败则原样返回。
    """
    if len(chars) < 2:
        return chars
    names = [c.name for c in chars]
    user = f"作品：{rec.ip_name}\n角色名列表：\n" + "\n".join(f"- {n}" for n in names)
    try:
        text = await _collect_text(llm_router, _CONSOLIDATE_SYSTEM, user, max_tokens=4096)
        data = _extract_json(text) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("ip_consolidate_failed", ip_name=rec.ip_name, error=str(exc))
        return chars
    groups = data.get("groups") or []
    if not groups:
        return chars

    alias_to_canon: dict[str, str] = {}
    for g in groups:
        if not isinstance(g, dict):
            continue
        canon = (g.get("canonical") or "").strip()
        if not canon:
            continue
        for a in [canon] + list(g.get("aliases") or []):
            key = _norm_name(a)
            if key:
                alias_to_canon[key] = canon

    by_canon: dict[str, IPCharacter] = {}
    for c in chars:
        canon = alias_to_canon.get(_norm_name(c.name), c.name)
        ck = _norm_name(canon)
        cur = by_canon.get(ck)
        if cur is None:
            by_canon[ck] = c.model_copy(update={"name": canon})
        else:
            richer = c if _char_info_len(c) > _char_info_len(cur) else cur
            by_canon[ck] = richer.model_copy(
                update={"name": canon, "must_have": cur.must_have or c.must_have}
            )
    merged = list(by_canon.values())
    if len(merged) < len(chars):
        logger.info(
            "ip_consolidated_characters",
            ip_name=rec.ip_name, before=len(chars), after=len(merged),
        )
    return merged


_ARBITRATE_SYSTEM = """你是 IP 设定的「总导演」。给你一个作品的角色清单 + 概述，你要做三件事，
保证下游据此生成的世界**自洽、不跨时代、不把多个版本糅成一锅**。

输出严格 JSON：
{
  "canon_note": "一句话说明本作的设定基线 / 锚定的版本或主线（若原作有多版本或多层设定被糅在一起，点明你锚定哪一个、其余视为旁支）",
  "playable_archetypes": ["建议玩家可扮演视角应覆盖的 3-6 类原型（如：主角 / 主要反派 / 灰色中立者 / 局外旁观者 / 受害者一方），让可玩视角不全挤在主角团"],
  "out_of_continuity": [
    {"name": "不该属于本作主线的角色原名（必须与清单里的名字一致）", "reason": "降级原因（≤20字）"}
  ]
}

判定 out_of_continuity 的铁律（**宁可少判，不可错杀**）：
1. **跨时代**：角色明显属于与本作主线**不同历史时期 / 不同朝代**的真实或虚构人物
   （例：汉末三国背景的作品里混进西汉的卫青 / 霍去病；明朝戏里混进清朝八旗姓氏角色）。
2. **跨版本糅合**：同一 IP 有互不相容的多个版本 / 多层世界观被拼接，角色明显只属于被你判为旁支的那一版。
3. **张冠李戴**：角色明显来自**另一部作品**，被错误塞了进来。

**绝不要**因为下列理由判 out_of_continuity（这些是合法设定，留着）：
- 玄幻 / 科幻 / 现代 / 都市 IP 里的穿越者 / 重生者 / 时间旅行者 —— 这是世界观本身，不是跨时代；
- 配角、龙套、戏份少、不出名 —— 厚度靠配角，不许以"不重要"为由降级；
- 反派、立场对立 —— 立场不是降级理由。
判不准时一律**保留**（不放进 out_of_continuity）。若全员都属于本作，out_of_continuity 返回 []。

只输出 JSON，无解释文字。"""


async def _arbitrate_canon(
    pack: IPKnowledgePack, rec: IPRecognition, llm_router: Any,
) -> IPKnowledgePack:
    """导演裁决（P1）：研究层尾部一次 LLM 收敛 —— 锚定版本/主线、滤跨时代角色、规划可玩生态位。

    **降级不删除**：被判 out_of_continuity 的角色就地标 in_continuity=False + must_have=False
    + arbitration_note（仍留在 pack.characters，可见可恢复），下游 canon_characters() 自动跳过。
    canon_note / playable_archetypes 落到 pack 上供 roster 规划消费。

    fail-open：LLM 失败 / 坏 JSON / 没产出 → 原样返回脏 pack（退回裁决前行为），绝不空世界。
    """
    if len(pack.characters) < 2:
        return pack
    roster_lines = "\n".join(
        f"- {c.name}（{c.role_in_story or '?'}；{c.relation_to_protagonist or '?'}）"
        for c in pack.characters
    )
    user = (
        f"作品：{rec.ip_name}（{rec.ip_type or 'other'}）\n"
        f"一句话：{rec.one_liner or ''}\n"
        f"概述：{(pack.summary or '')[:1200]}\n\n"
        f"角色清单：\n{roster_lines}"
    )
    try:
        # 判断类任务、开 reasoning 帮它推"是否跨时代/跨版本"。但 reasoning 会先吃 token 预算，
        # max_tokens 必须给足（实测 2048 被 ~2600 字思考吃光 → JSON 截断空 → 静默失败），
        # 给 8192；再解析失败就降级关思考重试一次（admin_generation 默认行为），照 roster 打法。
        text = await _collect_text(
            llm_router, _ARBITRATE_SYSTEM, user, max_tokens=8192, reasoning=True,
        )
        data = _extract_json(text)
        if not data:
            logger.warning(
                "ip_arbitrate_parse_failed_retrying_no_reasoning",
                ip_name=rec.ip_name, preview=text[:200],
            )
            text = await _collect_text(
                llm_router, _ARBITRATE_SYSTEM, user, max_tokens=8192, reasoning=False,
            )
            data = _extract_json(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ip_arbitrate_failed", ip_name=rec.ip_name, error=str(exc))
        return pack
    if not data:
        logger.warning("ip_arbitrate_empty", ip_name=rec.ip_name)
        return pack

    ooc_raw = data.get("out_of_continuity") or []
    ooc: dict[str, str] = {}
    for item in ooc_raw:
        if isinstance(item, dict) and item.get("name"):
            ooc[_norm_name(item["name"])] = str(item.get("reason") or "跨时代/跨版本，已降级")

    demoted: list[str] = []
    new_chars: list[IPCharacter] = []
    for c in pack.characters:
        reason = ooc.get(_norm_name(c.name))
        if reason:
            new_chars.append(c.model_copy(update={
                "in_continuity": False,
                "must_have": False,
                "arbitration_note": reason,
            }))
            demoted.append(c.name)
        else:
            new_chars.append(c)
    pack.characters = new_chars

    canon_note = str(data.get("canon_note") or "").strip() or None
    archetypes = [
        str(a).strip() for a in (data.get("playable_archetypes") or [])
        if isinstance(a, (str, int)) and str(a).strip()
    ][:8]
    pack.canon_note = canon_note
    pack.playable_archetypes = archetypes

    logger.info(
        "ip_arbitrated",
        ip_name=rec.ip_name,
        demoted=demoted,
        demoted_count=len(demoted),
        in_continuity=len(pack.canon_characters()),
        archetypes=len(archetypes),
        canon_note=(canon_note or "")[:80],
    )
    return pack


async def _gather_via_grok_fanout(
    rec: IPRecognition, grok_provider: Any | None,
) -> tuple[list[Passage], list[str]]:
    """C1: 同 4 轴并发 grok web_search → 富 passages + 候选名并集去重。

    grok 是生产唯一活源；多角度并行的并集远宽于单条大杂烩 query。
    """
    if grok_provider is None or not rec.ip_name:
        return [], []
    ip_type = rec.ip_type or "other"
    results = await asyncio.gather(
        *[
            fetch_via_grok_search(rec.ip_name, ip_type, grok_provider, focus=grok_focus)
            for _, grok_focus, _ in _RESEARCH_AXES
        ],
        return_exceptions=True,
    )
    passages: list[Passage] = []
    names: list[str] = []
    seen: set[str] = set()
    for r in results:
        if isinstance(r, BaseException):
            logger.warning("grok_fanout_axis_failed", ip_name=rec.ip_name, error=str(r))
            continue
        ps, cs = r
        passages.extend(ps)
        for n in cs:
            nn = _norm_name(n)
            if nn and nn not in seen:
                seen.add(nn)
                names.append(n)
    logger.info(
        "grok_fanout_done",
        ip_name=rec.ip_name, passages=len(passages), candidates=len(names),
    )
    return passages[:MAX_PASSAGES], names


async def build_ip_knowledge_pack(
    rec: IPRecognition,
    fidelity_mode: FidelityMode,
    llm_router: Any,
    tavily: Any,  # retained for signature compat; baidu/wiki/tavily 已退役不再使用
    grok_provider: Any | None = None,
    progress_cb: Callable[[str, str], Awaitable[None]] | None = None,
) -> IPKnowledgePack:
    """主入口（grok 多角度并行研究，2026-06-22 重写）。

    流程：
        Stage 1  per-axis pre-extract → merge   (4 轴并发凭训练知识抽取，按 _norm_name 合并)
        Stage 2  _gather_via_grok_fanout        (同 4 轴并发 grok web_search → 富 passages)
        Stage 3  _ground_and_augment            (passages 核查 + 补 source_passage_ids + 增删)
        Stage 4  self-check + grok 补抓 loop     (最多 MAX_REFETCH_ROUNDS 轮)
        Stage 5  quality gate                   (characters < _min_pack_characters → IPPackUnderfilledError)

    冷门 IP 主 LLM 不熟悉 → Stage 1 给空 / 单薄；grok 无果时走 pre-extract 兜底。

    progress_cb(code, message)：在每个真实子阶段边界回报，让前端 loading 标题/进度随检索→
    抽取→核对→查漏→整理逐步推进（而不是整段卡在"IP 知识抽取"+静止进度条）。
    """
    async def _emit(code: str, message: str) -> None:
        if progress_cb is None:
            return
        try:
            await progress_cb(code, message)
        except Exception:  # noqa: BLE001 — 进度回报不能影响主流程
            pass

    if rec.kind not in ("known_ip", "hybrid") or not rec.ip_name:
        return _empty_pack(rec, fidelity_mode)

    ip_type = rec.ip_type or "other"
    target = _target_characters(ip_type)
    ip_disp = rec.ip_name
    # 每轴目标取整体目标的一半——四轴并集覆盖整体目标，各轴聚焦自己那片挖深。
    per_axis_target = max(6, target // 2)

    await _emit("searching", f"正在联网检索《{ip_disp}》的原作资料…")

    # === Stage 1 + 2 并发：pre-extract(训练知识) ∥ grok fan-out(网络语料) ===
    # 两者互相独立（pre-extract 不喂 passages、grok 用固定 axes 不依赖 pre-extract 结果），
    # 只在 Stage 3 ground 时汇合 → 串行白白多等一段，并发可省约一个 stage 的墙钟时间。
    async def _run_pre_extract() -> list:
        return await asyncio.gather(
            *[
                _pre_extract_canon(
                    rec, llm_router, focus_hint=hint, target_chars=per_axis_target,
                )
                for _, _, hint in _RESEARCH_AXES
            ],
            return_exceptions=True,
        )

    pre_results, (passages, _cand_names) = await asyncio.gather(
        _run_pre_extract(),
        _gather_via_grok_fanout(rec, grok_provider),
    )
    pre_packs = [p for p in pre_results if isinstance(p, IPKnowledgePack)]
    for r in pre_results:
        if isinstance(r, BaseException):
            logger.warning("ip_pre_extract_axis_failed", ip_name=rec.ip_name, error=str(r))
    candidates_pack = (
        _merge_packs(pre_packs, rec, "none") if pre_packs else _empty_pack(rec, "none")
    )
    logger.info(
        "ip_pre_extract_fanout_done",
        ip_name=rec.ip_name,
        axes=len(pre_packs),
        characters=len(candidates_pack.characters),
        places=len(candidates_pack.places),
        factions=len(candidates_pack.factions),
        summary_len=len(candidates_pack.summary),
    )
    await _emit(
        "extracted",
        f"已检索原作资料，抽取到 {len(candidates_pack.characters)} 个角色 · "
        f"{len(candidates_pack.places)} 个地点",
    )

    # === Stage 3: ground & augment ===
    if not passages:
        # 无外部语料（grok 无果 / 未配置）→ 返回 merge 后的 pre-extract pack 兜底。
        logger.warning("ip_research_no_passages", ip_name=rec.ip_name)
        pack = candidates_pack
        pack.fidelity_mode = fidelity_mode
        pack.passages = []
    else:
        await _emit("grounding", "正在核对史料、补全人物与设定细节…")
        pack = await _ground_and_augment(
            rec, candidates_pack, passages, fidelity_mode, llm_router,
            target_chars=target,
        )

    # === Stage 4: self-check + grok 补抓 loop ===
    for _ in range(MAX_REFETCH_ROUNDS):
        missing = await _self_check_missing_v2(pack, llm_router)
        missing_names = missing["missing_characters"] + missing["missing_places"]
        if not missing_names:
            break
        if grok_provider is None:
            break
        await _emit("refining", "查漏补缺，补抓遗漏的角色与设定…")
        # 退死源后，补抓也走 grok：用缺失名拼一条聚焦 query。
        extra_passages, _ = await fetch_via_grok_search(
            rec.ip_name, ip_type, grok_provider, focus=" ".join(missing_names),
        )
        if not extra_passages:
            break
        passages = (passages + extra_passages)[:MAX_PASSAGES]
        pack = await _ground_and_augment(
            rec, pack, passages, fidelity_mode, llm_router, target_chars=target,
        )

    # === Stage 4.5: 归并名称变体（fan-out 多轴并发会让同一人出现多种叫法）===
    await _emit("consolidating", "正在整理角色档案、归并别名…")
    pack.characters = await _consolidate_characters(pack.characters, rec, llm_router)

    # === Stage 4.6: 导演裁决（P1）—— 锚定版本/主线、滤跨时代角色、规划可玩生态位 ===
    # 放在持久化之前 → 落库的 pack 本身就干净（同时治 DB 污染），下游 canon_characters()
    # 自动跳过被降级的角色，编排零改动。fail-open：失败原样放行。
    await _emit("arbitrating", "正在校准设定基线、剔除跨时代/跨版本人物…")
    pack = await _arbitrate_canon(pack, rec, llm_router)

    # === Stage 5: quality gate（只数续作内角色，被降级的不算厚度）===
    if len(pack.canon_characters()) < _min_pack_characters(ip_type):
        raise IPPackUnderfilledError(
            ip_name=rec.ip_name,
            character_count=len(pack.canon_characters()),
            summary_len=len(pack.summary),
        )

    logger.info(
        "ip_research_done",
        ip_name=rec.ip_name,
        characters=len(pack.characters),
        in_continuity=len(pack.canon_characters()),
        must_have=len(pack.must_have_character_names()),
        places=len(pack.places),
        factions=len(pack.factions),
        passages=len(pack.passages),
    )
    return pack
