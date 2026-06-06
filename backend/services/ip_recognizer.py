"""Stage 0：从用户自由文本识别是否指向某个已知 IP。

输出 IPRecognition：kind / confidence / ip_name / ip_type / one_liner / source_hints
后续 Stage A+ 仅当 kind in (known_ip, hybrid) 时执行 IP Research。
"""
import json
import re
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field, field_validator

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

特别注意：
- 如果输入文本包含具体作品名（《XX》/「XX」/影视剧 XX），即使你不确定该作品是否真实存在（如训练截止后的新作），也应输出 kind=known_ip 且 confidence=0.7，由后续 Tavily 验证调整。
- 纯描述性、无作品名的输入（如"未来火星上的官僚社会"）输出 kind=original。

严格 JSON 输出，无解释文字。"""


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
    try:
        text = await _collect_text(llm_router, _RECOGNIZER_SYSTEM, description)
        data = _extract_json(text)
        if not data:
            logger.warning("ip_recognition_parse_failed", text_preview=text[:200])
            return IPRecognition(kind="original", confidence=0.0)
        rec = IPRecognition(
            kind=data.get("kind", "original"),
            confidence=float(data.get("confidence", 0.0)),
            ip_name=data.get("ip_name"),
            ip_type=data.get("ip_type"),
            one_liner=data.get("one_liner"),
            source_hints=data.get("source_hints") or [],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ip_recognition_failed", error=str(exc))
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
