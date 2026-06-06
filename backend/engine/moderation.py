from __future__ import annotations

import json
from dataclasses import dataclass, field

import structlog

from llm.router import LLMRouter
from llm.usage_context import usage_context

logger = structlog.get_logger()

CATEGORIES = ("violence", "sexual", "hate", "self_harm", "illegal")
THRESHOLDS_INPUT = {"violence": 8, "sexual": 7, "hate": 7, "self_harm": 8, "illegal": 8}
THRESHOLDS_OUTPUT = {"violence": 6, "sexual": 5, "hate": 5, "self_harm": 5, "illegal": 6}

LOCAL_KEYWORD_RULES: tuple[tuple[str, str, int], ...] = (
    ("制造炸弹", "illegal", 10),
    ("制造武器", "illegal", 9),
    ("制毒", "illegal", 10),
    ("杀掉所有", "violence", 8),
    ("自杀", "self_harm", 8),
)


@dataclass
class ModerationResult:
    allowed: bool
    scores: dict[str, int] = field(default_factory=dict)
    flagged_categories: list[str] = field(default_factory=list)
    reason: str | None = None
    source: str = "local"


MODERATION_TOOL = {
    "name": "report_moderation_scores",
    "description": "Return safety scores for a InkWild gameplay text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "violence": {"type": "integer", "minimum": 0, "maximum": 10},
            "sexual": {"type": "integer", "minimum": 0, "maximum": 10},
            "hate": {"type": "integer", "minimum": 0, "maximum": 10},
            "self_harm": {"type": "integer", "minimum": 0, "maximum": 10},
            "illegal": {"type": "integer", "minimum": 0, "maximum": 10},
            "reason": {"type": "string"},
        },
        "required": ["violence", "sexual", "hate", "self_harm", "illegal"],
    },
}

MODERATION_SYSTEM_PROMPT = """\
你是 InkWild 的内容安全分类器。请只评估文本本身的安全风险，不续写剧情。
给每个分类打 0-10 分：0 表示无风险，10 表示严重违规。
分类：
- violence: 现实暴力伤害、血腥细节、威胁
- sexual: 性内容或露骨性描写
- hate: 仇恨、歧视或针对受保护群体的攻击
- self_harm: 自残、自杀或鼓励自我伤害
- illegal: 违法操作指导、武器/爆炸物/毒品制作等
使用工具 report_moderation_scores 返回分数。
"""


def _thresholds(scope: str) -> dict[str, int]:
    return THRESHOLDS_OUTPUT if scope == "output" else THRESHOLDS_INPUT


def _coerce_score(value: object) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(10, score))


def _result_from_scores(
    scores: dict[str, int],
    *,
    scope: str,
    reason: str | None = None,
    source: str,
) -> ModerationResult:
    thresholds = _thresholds(scope)
    normalized_scores = {category: _coerce_score(scores.get(category, 0)) for category in CATEGORIES}
    flagged = [
        category
        for category in CATEGORIES
        if normalized_scores[category] >= thresholds[category]
    ]
    return ModerationResult(
        allowed=not flagged,
        scores=normalized_scores,
        flagged_categories=flagged,
        reason=reason,
        source=source,
    )


def classify_locally(text: str, *, scope: str = "input") -> ModerationResult:
    scores = {category: 0 for category in CATEGORIES}
    reasons: list[str] = []
    for keyword, category, score in LOCAL_KEYWORD_RULES:
        if keyword in text:
            scores[category] = max(scores[category], score)
            reasons.append(keyword)
    reason = "命中本地安全规则：" + "、".join(reasons) if reasons else None
    return _result_from_scores(scores, scope=scope, reason=reason, source="local")


def _extract_json_from_text(text: str) -> dict | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def classify(
    text: str,
    *,
    scope: str = "input",
    llm_router: LLMRouter | None = None,
) -> ModerationResult:
    if llm_router is None:
        return classify_locally(text, scope=scope)

    tool_payload: dict | None = None
    text_parts: list[str] = []
    try:
        # Override inherited ``game`` purpose so moderation spend is
        # bucketed separately in admin analytics.
        with usage_context(purpose="moderation"):
            async for event in llm_router.stream_with_tools(
                messages=[{"role": "user", "content": text}],
                tools=[MODERATION_TOOL],
                system=MODERATION_SYSTEM_PROMPT,
                max_tokens=256,
            ):
                if event.get("type") == "tool_use" and event.get("name") == MODERATION_TOOL["name"]:
                    payload = event.get("input")
                    if isinstance(payload, dict):
                        tool_payload = payload
                elif event.get("type") == "text_delta" and isinstance(event.get("text"), str):
                    text_parts.append(event["text"])
                elif event.get("type") == "usage":
                    continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("moderation_llm_failed", scope=scope, error=str(exc), exc_info=True)
        return classify_locally(text, scope=scope)

    payload = tool_payload or _extract_json_from_text("".join(text_parts)) or {}
    result = _result_from_scores(
        {category: _coerce_score(payload.get(category, 0)) for category in CATEGORIES},
        scope=scope,
        reason=str(payload.get("reason") or "") or None,
        source="llm",
    )
    return result
