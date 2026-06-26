"""Stage 0：从用户自由文本识别是否指向某个已知 IP。

输出 IPRecognition：kind / confidence / ip_name / ip_type / one_liner / source_hints
后续 Stage A+ 仅当 kind in (known_ip, hybrid) 时执行 IP Research。
"""
import json
import re
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field, field_validator

from config import settings
from services.world_creator_retry import TransientError, with_transient_retry

logger = structlog.get_logger()

IPKind = Literal["known_ip", "hybrid", "original"]
IPType = Literal["tv", "movie", "novel", "anime", "game", "other"]

# Tavily verification thresholds — only verify when LLM confidence is in this window.
_TAVILY_VERIFY_MIN = 0.6
_TAVILY_VERIFY_MAX = 0.85
# Confidence adjustments after Tavily verification.
_CONFIDENCE_PROMOTE_DELTA = 0.15
_CONFIDENCE_PROMOTE_CEIL = 0.95
_CONFIDENCE_DEMOTE_DELTA = 0.20
_CONFIDENCE_DEMOTE_FLOOR = 0.40
# Below this confidence after demotion, downgrade kind from known_ip → hybrid.
_HYBRID_DOWNGRADE_THRESHOLD = 0.50


class IPRecognition(BaseModel):
    kind: IPKind
    confidence: float = Field(ge=0.0, le=1.0)
    ip_name: str | None = None
    ip_type: IPType | None = None
    one_liner: str | None = None
    source_hints: list[str] = Field(default_factory=list)

    @field_validator("source_hints", mode="before")
    @classmethod
    def _coerce_source_hints(cls, v: Any) -> list[str]:
        # LLM 偶尔会把 source_hints 输出成字符串（如 "逐玉 电视剧, 逐玉 影视"）
        # 或单字符串而非数组；这里统一兜底成 list[str]。
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [p.strip() for p in re.split(r"[,，;；\n]", v) if p.strip()]
        if isinstance(v, list):
            return [str(x).strip() for x in v if x is not None and str(x).strip()]
        return []


_RECOGNIZER_SYSTEM = """你判断用户输入的世界描述是否指向某个已知 IP（影视剧 / 小说 / 动漫 / 游戏）。

判定步骤（务必照做）：
第一步：先问自己——"我能不能说出这个输入对应的具体作品？它的主角 / 作者 / 标志设定是什么？"
第二步：只要第一步能答上来（哪怕输入没有书名号、只是裸名字，如"哈利波特""甄嬛传"），kind 就必须是 "known_ip"，ip_name 必填，confidence ≥ 0.85。
第三步：输入含书名号作品名（《XX》/「XX」）但你不确定是否真实存在（如训练截止后的新作）时，仍输出 kind="known_ip" 且 confidence=0.7，由后续验证调整。
第四步：若输入下方附带【联网检索资料】，以它为最高优先依据——很多看似普通词组的标题其实是具体作品（尤其网络小说，标题如《十日终焉》《诡秘之主》）。检索资料指向某部具体作品 → kind="known_ip"，按资料填 ip_name / ip_type / 作者；检索资料明确说"非特定作品 / 查无此作"时，才维持 original。
第五步：只有当输入纯描述性、且（无检索资料、或检索确认非特定作品）对应不到任何已有作品时，才输出 kind="original"。

铁律：如果你的 one_liner 里写出了具体作品名 / 主角 / 作者 / 标志地点，kind 绝不能是 original。

参考示例：
输入"哈利波特" → {"kind":"known_ip","confidence":0.95,"ip_name":"哈利·波特","ip_type":"novel","one_liner":"少年巫师在霍格沃茨对抗伏地魔","source_hints":["哈利·波特 J.K.罗琳"]}
输入"甄嬛传" → {"kind":"known_ip","confidence":0.95,"ip_name":"甄嬛传","ip_type":"tv","one_liner":"清宫嫔妃甄嬛的后宫沉浮","source_hints":["甄嬛传 流潋紫"]}
输入"十日终焉"（附检索资料：番茄小说无限流网文，作者杀虫队队员，主角齐夏） → {"kind":"known_ip","confidence":0.9,"ip_name":"十日终焉","ip_type":"novel","one_liner":"齐夏进入终焉之地参与十日生存游戏","source_hints":["十日终焉 杀虫队队员"]}
输入"未来火星上的官僚制蜗牛社会" → {"kind":"original","confidence":0.9,"ip_name":null,"ip_type":"other","one_liner":"火星蜗牛官僚的荒诞设定","source_hints":[]}

输出 JSON，字段：
- kind: known_ip / hybrid（混合多个 IP 或借鉴）/ original
- confidence: 0~1
- ip_name: known_ip / hybrid 时必填
- ip_type: tv / movie / novel / anime / game / other
- one_liner: 一句话简介（30 字内）
- source_hints: 推荐查询关键词数组（如百度百科 / 维基条目名）

严格 JSON 输出，无解释文字。"""


async def build_recognizer_llm(db: Any, fallback: Any | None = None) -> Any | None:
    """识别步 LLM：走 `ip_recognition` 槽绑定（admin 后台可管），未绑/解析失败回退到 fallback。

    IP 识别是整条 IP 链路的闸门——只有判成 known_ip / hybrid 才触发后续联网研究与复刻。
    生成主模型（DeepSeek）离线、知识旧，认不出较新作品 → IP 世界被误判「原创」，所以识别
    需要带联网（Live Search）能力的 grok 模型。

    **统一走 slot 体系**（与其余槽一致、admin 可改，不再硬编码 provider/model）：
    `resolve_slot_provider` 取 `ip_recognition` 槽绑定的 provider；未绑定时其
    `_legacy_text_router` 用 `ip_recognition_model`（grok-4.3-fast）建 grok 兜底；grok 完全
    未配置时返回 `fallback`（生成主模型，退化为纯参数判断、web_search 兜底自动失效）。
    """
    try:
        from services.model_management import resolve_slot_provider

        provider = await resolve_slot_provider(db, "ip_recognition")
        if provider is not None:
            return provider
    except Exception as exc:  # noqa: BLE001
        logger.warning("recognizer_slot_resolve_failed", error=str(exc))
    return fallback


async def _collect_text(llm_router: Any, system: str, user: str, max_tokens: int = 512) -> str:
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


async def _tavily_verify(ip_name: str, tavily: Any | None) -> bool:
    """快速验证：Tavily 搜 ip_name，看是否任一前几条结果的标题或 URL 包含 ip_name。

    CJK 字符没有 case 概念，lower() 对中文是 no-op，但保留以兼容混合英文 IP。
    检查多条结果（而非只第一条），因为 Wikipedia/百度的标题常带消歧后缀
    （如「逐玉 (电视剧)」），但 ip_name 仍是子串。
    """
    if tavily is None or not ip_name:
        return False
    try:
        results = await tavily.search(query=ip_name, max_results=3)
        if not results:
            return False
        needle = ip_name.lower()
        for r in results:
            title = (r.get("title") or "").lower()
            url = (r.get("url") or "").lower()
            if needle in title or needle in url:
                return True
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("tavily_verify_failed", ip_name=ip_name, error=str(exc))
        return False


async def _web_search_evidence(llm_router: Any, description: str) -> str:
    """识别兜底取证：用识别器自己的 grok 模型（ip_recognition_model，当前 grok-4.3-fast）
    做 Live Search，查"这个描述是不是某部具体作品"。

    离线主模型 / grok 参数知识认不出较新作品（典型：网文标题像普通词组，如「十日终焉」），
    把真 IP 误判成 original → 整条 IP 研究 / 裁决链路被跳过。这里在参数判断说 original 时
    补一次联网检索，把证据喂回判断。**与判断步同一个 grok 模型、不另起 provider**（实测
    grok-4.3-fast Live Search 对「十日终焉」返回作者/主角/类型 + 15 条引用）；llm_router
    不支持 web_search（如回退到离线主模型）时返回空串，退回纯参数行为。
    """
    web_search = getattr(llm_router, "web_search", None)
    if not callable(web_search):
        return ""
    query = (
        f"「{description}」是否对应某一部已知的具体作品（小说 / 网络小说 / 电视剧 / 电影 / "
        f"动漫 / 游戏）？若是，给出：作品全名、类型、作者或出品方、主角、一句话简介。"
        f"若它只是一个泛泛的概念或设定短语、并非某部具体作品，请明确回答「非特定作品」。"
        f"注意：有些作品名看起来像很普通的词组，但其实是具体作品（尤其网络小说）。"
    )
    try:
        res = await web_search(query)
        return (getattr(res, "text", "") or "").strip()[:1500]
    except Exception as exc:  # noqa: BLE001
        logger.warning("ip_recognition_web_search_failed", error=str(exc))
        return ""


async def recognize_ip(description: str, llm_router: Any, tavily: Any | None = None) -> IPRecognition:
    """Stage 0：识别 description 指向的 IP。失败时返回 original/0.0。

    两遍判定：① 参数知识 best-of-N 快判；② 若快判说 original / 没填 ip_name，再用
    Grok Live Search 取证复判一次——解决裸标题网文（如「十日终焉」）被误判成原创、整条
    IP 链路被跳过的问题。known_ip 命中即采用；纯参数命中的著名 IP 不触发联网，省延迟。
    """
    if not description.strip():
        return IPRecognition(kind="original", confidence=0.0)

    async def _attempt(evidence: str = "") -> IPRecognition:
        user = description
        if evidence:
            user = (
                f"用户输入：{description}\n\n"
                f"【联网检索资料（可能含噪声，作判断依据，勿照抄）】\n{evidence}"
            )
        text = await _collect_text(llm_router, _RECOGNIZER_SYSTEM, user)
        data = _extract_json(text)
        if not data:
            logger.warning("ip_recognition_parse_failed", text_preview=text[:200])
            raise TransientError("ip_recognition JSON 解析失败")
        # 空串归一为 None：模型偶尔回 ip_type=""，会撞 Literal 校验报错把整票丢掉
        # （best-of-N 下等于白丢一票，极端情况漏掉唯一判 known_ip 的那票）。
        return IPRecognition(
            kind=data.get("kind") or "original",
            confidence=float(data.get("confidence", 0.0)),
            ip_name=data.get("ip_name") or None,
            ip_type=data.get("ip_type") or None,
            one_liner=data.get("one_liner") or None,
            source_hints=data.get("source_hints") or [],
        )

    def _is_hit(r: IPRecognition | None) -> bool:
        return r is not None and r.kind in ("known_ip", "hybrid") and bool((r.ip_name or "").strip())

    # Pass 1 —— Best-of-N 参数知识快判：fast 模型 kind 会抖动（著名 IP 偶判 original），多打
    # 几次任一次判 known_ip/hybrid 且填了 ip_name 就采用。每次内部仍带瞬态重试。
    votes = max(1, settings.ip_recognition_votes)
    rec: IPRecognition | None = None
    for i in range(votes):
        try:
            cand = await with_transient_retry(lambda: _attempt(""), max_attempts=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ip_recognition_failed", attempt=i + 1, error=str(exc))
            continue
        if _is_hit(cand):
            rec = cand  # 命中即采用，提前结束
            break
        # 记下首个非异常结果作为兜底（多为 original）
        if rec is None:
            rec = cand

    # Pass 2 —— 参数判 original / 没填 ip_name 时，联网取证复判一次（兜住裸标题网文等漏判）。
    if not _is_hit(rec):
        evidence = await _web_search_evidence(llm_router, description)
        if evidence:
            try:
                cand = await with_transient_retry(lambda: _attempt(evidence), max_attempts=2)
                if _is_hit(cand):
                    logger.info(
                        "ip_recognition_rescued_by_search",
                        description=description[:40], ip_name=cand.ip_name,
                    )
                    rec = cand
            except Exception as exc:  # noqa: BLE001
                logger.warning("ip_recognition_search_rescue_failed", error=str(exc))

    if rec is None:
        return IPRecognition(kind="original", confidence=0.0)

    # Tavily 二次验证：known_ip 且 0.6~0.85 区间时才需要
    if rec.kind == "known_ip" and rec.ip_name and _TAVILY_VERIFY_MIN <= rec.confidence <= _TAVILY_VERIFY_MAX:
        verified = await _tavily_verify(rec.ip_name, tavily)
        if verified:
            rec.confidence = min(_CONFIDENCE_PROMOTE_CEIL, rec.confidence + _CONFIDENCE_PROMOTE_DELTA)
        else:
            rec.confidence = max(_CONFIDENCE_DEMOTE_FLOOR, rec.confidence - _CONFIDENCE_DEMOTE_DELTA)
            if rec.confidence < _HYBRID_DOWNGRADE_THRESHOLD:
                rec.kind = "hybrid"  # 降级为模糊借鉴
    return rec
