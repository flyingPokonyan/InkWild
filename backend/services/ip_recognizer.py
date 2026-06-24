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

输出 JSON，字段：
- kind: "known_ip"（明确指向某 IP）/ "hybrid"（混合多个 IP 或借鉴）/ "original"（原创世界）
- confidence: 0~1
- ip_name: known_ip / hybrid 时必填
- ip_type: tv / movie / novel / anime / game / other
- one_liner: 一句话简介（30 字内）
- source_hints: 推荐查询关键词（如百度百科 / 维基条目名）

判定规则（务必遵守，按优先级）：
1. 只要输入指向一个你能识别的具体作品——你能说出它的主角 / 作者 / 标志性设定——就必须输出 kind="known_ip" 且填 ip_name，confidence ≥ 0.8。**不要因为输入没有书名号就降级为 original**（如"哈利波特""甄嬛传"这种裸作品名也是 known_ip）。
2. 一致性铁律：如果你的 one_liner 里点到了具体作品名 / 主角 / 作者 / 标志地点，kind 绝不能是 original——必须是 known_ip 或 hybrid，ip_name 必填。
3. 输入含书名号作品名（《XX》/「XX」）但你不确定是否真实存在（如训练截止后的新作）时，仍输出 kind=known_ip 且 confidence=0.7，由后续验证调整。
4. kind="original" 仅用于：纯描述性、不对应任何已有作品的原创设定（如"未来火星上的官僚社会"）。

严格 JSON 输出，无解释文字。"""


def build_recognizer_llm(fallback: Any | None = None) -> Any | None:
    """识别步专用 LLM：优先 Grok 快速模型，未配置/构造失败时回退到 fallback。

    IP 识别是整条 IP 链路的闸门——只有判成 known_ip / hybrid 才会触发后续联网研究
    与 IP 复刻。生成主模型（DeepSeek）离线、知识旧，认不出较新的作品（如新剧），
    导致 IP 世界被误判为「原创」。Grok 网关后端有实时联网能力，因此识别步专门走
    grok-4.3-fast。fallback 一般传生成主模型，保证 Grok 未配置时仍能退化运行。
    """
    if not settings.grok_api_key:
        return fallback
    try:
        from llm.grok import GrokProvider

        return GrokProvider(model=settings.ip_recognition_model)
    except Exception as exc:  # noqa: BLE001
        logger.warning("recognizer_llm_build_failed", error=str(exc))
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


async def recognize_ip(description: str, llm_router: Any, tavily: Any | None = None) -> IPRecognition:
    """Stage 0：识别 description 指向的 IP。失败时返回 original/0.0。"""
    if not description.strip():
        return IPRecognition(kind="original", confidence=0.0)

    async def _attempt() -> IPRecognition:
        text = await _collect_text(llm_router, _RECOGNIZER_SYSTEM, description)
        data = _extract_json(text)
        if not data:
            logger.warning("ip_recognition_parse_failed", text_preview=text[:200])
            raise TransientError("ip_recognition JSON 解析失败")
        return IPRecognition(
            kind=data.get("kind", "original"),
            confidence=float(data.get("confidence", 0.0)),
            ip_name=data.get("ip_name"),
            ip_type=data.get("ip_type"),
            one_liner=data.get("one_liner"),
            source_hints=data.get("source_hints") or [],
        )

    # Best-of-N 投票：fast 模型的 kind 字段会抖动（同一著名 IP 偶尔判 original），但每次
    # 都"认得"内容。多打几次，任一次判 known_ip/hybrid 且填了 ip_name 就采用——直接消除
    # 抖动。每次内部仍带瞬态重试（覆盖网关偶发错误 / 解析失败）。
    votes = max(1, settings.ip_recognition_votes)
    rec: IPRecognition | None = None
    for i in range(votes):
        try:
            cand = await with_transient_retry(_attempt, max_attempts=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ip_recognition_failed", attempt=i + 1, error=str(exc))
            continue
        if cand.kind in ("known_ip", "hybrid") and (cand.ip_name or "").strip():
            rec = cand  # 命中即采用，提前结束
            break
        # 记下首个非异常结果作为兜底（多为 original）
        if rec is None:
            rec = cand
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
