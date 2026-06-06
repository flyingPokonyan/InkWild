from dataclasses import dataclass, field

from config import settings
from engine.moderation import ModerationResult, classify, classify_locally
from llm.router import LLMRouter


@dataclass
class FilterResult:
    is_safe: bool
    reason: str | None = None
    flagged_categories: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)
    source: str = "local"


def _reason(prefix: str, result: ModerationResult) -> str | None:
    if result.allowed:
        return None
    return prefix


def _to_filter_result(result: ModerationResult, *, unsafe_prefix: str) -> FilterResult:
    return FilterResult(
        is_safe=result.allowed,
        reason=_reason(unsafe_prefix, result),
        flagged_categories=result.flagged_categories,
        scores=result.scores,
        source=result.source,
    )


def check_input(text: str) -> FilterResult:
    return _to_filter_result(classify_locally(text, scope="input"), unsafe_prefix="包含违规内容")


def check_output(text: str) -> FilterResult:
    return _to_filter_result(classify_locally(text, scope="output"), unsafe_prefix="AI 输出包含违规内容")


async def check_input_moderated(text: str, *, llm_router: LLMRouter | None = None) -> FilterResult:
    # When the content filter is disabled (e.g. pre-launch self-testing) we skip
    # the LLM moderation call entirely and fall back to the zero-latency local
    # keyword guard, which still blocks the hard illegal cases.
    if not settings.content_filter_enabled:
        return check_input(text)
    return _to_filter_result(
        await classify(text, scope="input", llm_router=llm_router),
        unsafe_prefix="包含违规内容",
    )


async def check_output_moderated(text: str, *, llm_router: LLMRouter | None = None) -> FilterResult:
    if not settings.content_filter_enabled:
        return check_output(text)
    return _to_filter_result(
        await classify(text, scope="output", llm_router=llm_router),
        unsafe_prefix="AI 输出包含违规内容",
    )
