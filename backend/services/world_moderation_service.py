"""World moderation pass (spec §5.5).

抽样自由文本字段调 moderation 接口，命中字段标 'moderation_flag:<reason>' warning。
不阻断 — 由 publish_world_draft 检查 quality_warnings 决定是否拦截发布。
"""
from __future__ import annotations

from typing import Awaitable, Callable

import structlog

logger = structlog.get_logger()

ModerationResult = dict  # {"flagged": bool, "reasons": list[str]}
ModerationCallable = Callable[[str], Awaitable[ModerationResult]]


def extract_moderation_flags(quality_warnings: list[str]) -> list[str]:
    """从 quality_warnings 列表中提取 'moderation_flag:<reason>' 的 reason 部分（保留重复）。"""
    flags: list[str] = []
    for w in quality_warnings or []:
        if isinstance(w, str) and w.startswith("moderation_flag:"):
            flags.append(w[len("moderation_flag:"):])
    return flags


async def _check_text(callable_: ModerationCallable, text: str) -> list[str]:
    """对单条文本调 moderation_callable，返回 reasons list。失败 → []"""
    if not text or not text.strip():
        return []
    try:
        result = await callable_(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("moderation_call_failed", error=str(exc))
        return []
    if not isinstance(result, dict):
        return []
    if not result.get("flagged"):
        return []
    reasons = result.get("reasons") or []
    return [str(r) for r in reasons if r]


async def moderate_world_payload(
    payload: dict,
    moderation_callable: ModerationCallable,
    *,
    sample_passages: int = 5,
) -> list[str]:
    """抽样字段调 moderation 接口，返回 'moderation_flag:<reason>' warning list。

    moderation_callable 接受单个文本字符串，返回 dict 形态：
        {"flagged": bool, "reasons": list[str]}

    本函数不阻断 — 总是返回 warnings list（可能空）。
    """
    warnings: list[str] = []

    def _take(items: list, key: str) -> list[str]:
        """从 items 前 sample_passages 条中取 key 字段值。"""
        return [x.get(key, "") for x in items[:sample_passages] if isinstance(x, dict)]

    chars: list = payload.get("world_characters") or []

    # personality（每人一条，最多 sample_passages 条）
    for text in _take(chars, "personality"):
        for r in await _check_text(moderation_callable, text):
            warnings.append(f"moderation_flag:{r}")

    # secret（同上）
    for text in _take(chars, "secret"):
        for r in await _check_text(moderation_callable, text):
            warnings.append(f"moderation_flag:{r}")

    # shared_events.summary
    for text in _take(payload.get("shared_events") or [], "summary"):
        for r in await _check_text(moderation_callable, text):
            warnings.append(f"moderation_flag:{r}")

    # events_data.summary
    for text in _take(payload.get("events_data") or [], "summary"):
        for r in await _check_text(moderation_callable, text):
            warnings.append(f"moderation_flag:{r}")

    # lore_pack content_blocks.body（跨 dimension 合并计数，总计 ≤ sample_passages 条）
    lore_pack: dict = payload.get("lore_pack") or {}
    blocks_seen = 0
    for dim in (lore_pack.get("dimensions") or []):
        if blocks_seen >= sample_passages:
            break
        for block in (dim.get("content_blocks") or []):
            if blocks_seen >= sample_passages:
                break
            blocks_seen += 1
            text = block.get("body", "") if isinstance(block, dict) else ""
            for r in await _check_text(moderation_callable, text):
                warnings.append(f"moderation_flag:{r}")

    return warnings
