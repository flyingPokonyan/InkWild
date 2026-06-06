"""Recent-messages filter for narrator weave context.

避免 narrator 锚定到自己过去的 env-only 输出（BUGS #27 H3，详见
docs/plans/narrator-simplification-2026-05.md）。
对 assistant role 消息检测 dialogue 特征（中/英/法式引号），不带的就剔除；
user / system role 一律保留以维持上下文 + 时间线。

只在 narrator weave 调用前用，不影响 director / NPC agent 的 recent_messages。
"""
from __future__ import annotations

# 中文 / 英文 / 法式 / 弯引号都算 dialogue 特征
_QUOTE_CHARS = ("「", "」", "『", "』", "“", "”", '"', "‘", "’", "'")


def _has_dialogue_markers(content: str) -> bool:
    return any(ch in content for ch in _QUOTE_CHARS)


def filter_recent_messages_for_narrator(messages: list[dict]) -> list[dict]:
    """Filter narrator weave's recent_messages: drop env-only assistant rows.

    保留：
    - 所有 user / system role 消息（维持上下文 + 时间线）
    - 含 dialogue 特征的 assistant 消息（"working examples"）

    剔除：
    - assistant role 且不含任何引号的消息（env-only 锚点，会污染 LLM 风格）
    """
    return [
        m for m in messages
        if m.get("role") != "assistant" or _has_dialogue_markers(m.get("content", ""))
    ]
