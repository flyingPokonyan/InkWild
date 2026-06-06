"""Semantic consistency review for world + script artifacts.

cross_artifact_validator catches schema-level drift (event references unknown
NPC, ending requires unspawned clue). It cannot tell that ``events_data``
implies NPC-A is the killer while ``endings_data`` reveals the player
character is the real killer — semantically incoherent but referentially
valid. BUGS #24.

Warn-only by design. A semantic issue is a signal the generator drifted,
not a hard blocker — publish proceeds and the warnings surface to admin via
audit log + structured logging. Cost is one cheap LLM call (~$0.01-0.02).
"""
from __future__ import annotations

import json

import structlog

from llm.router import LLMRouter

logger = structlog.get_logger()

_SYSTEM_PROMPT = """你是剧本一致性审查员。你会拿到一个世界 + 一份剧本的关键结构化片段（事件、结局、人物名册）。
你的唯一任务：识别**剧情层面**（不是 schema 层）的自相矛盾。

要重点检查的不一致类型：
1. 反派 / 凶手 / 幕后黑手身份的指认是否前后一致（events 里暗示 A 是黑手，但 ending 揭露 B 是真凶 → 矛盾）
2. 互斥结局是否同时被设为"可达"（例如多个结局都声称是"唯一真相"）
3. 关键反转链是否断裂（假解答 → 真解答应有线索铺垫；如缺失则记录）
4. NPC 阵营 / 关系是否被结局推翻得过于离谱（IP fidelity 层面：原著明确为对手的两人不能被设为亲属）

不要管：
- 文风 / 用词 / 描写质量
- 难度 / 节奏
- schema 完整性（已有 validator 管）

只输出 JSON：{"issues": ["issue 1 description", "issue 2 description"]}。
没有问题就输出 {"issues": []}。每条 issue 中文，一句话，引用具体事件/结局 id。"""


def _build_user_message(world: dict, script: dict) -> str:
    """Compact rendering of artifacts that fits in one prompt without
    re-serializing the full dicts."""

    lines: list[str] = []

    chars = world.get("characters") or []
    if chars:
        lines.append("## 人物名册")
        for c in chars:
            if not isinstance(c, dict):
                continue
            name = c.get("name") or "?"
            role = c.get("role") or c.get("personality_summary") or ""
            secret = c.get("secret") or ""
            line = f"- {name}"
            if role:
                line += f"：{role[:80]}"
            if secret:
                line += f"（秘密：{secret[:80]}）"
            lines.append(line)
        lines.append("")

    events = list(world.get("events_data") or []) + list(script.get("events_data") or [])
    if events:
        lines.append("## 事件 events_data")
        for ev in events:
            if not isinstance(ev, dict):
                continue
            ev_id = ev.get("id") or "?"
            summary = (ev.get("summary") or "")[:200]
            lines.append(f"- [{ev_id}] {summary}")
        lines.append("")

    endings = script.get("endings_data") or []
    if endings:
        lines.append("## 结局 endings_data")
        for end in endings:
            if not isinstance(end, dict):
                continue
            end_id = end.get("id") or end.get("ending_type") or "?"
            title = end.get("title") or ""
            desc = (end.get("description") or "")[:300]
            lines.append(f"- [{end_id}] {title}")
            if desc:
                lines.append(f"  {desc}")
        lines.append("")

    lines.append("请按系统提示输出 JSON。")
    return "\n".join(lines)


async def check_semantic_consistency(
    world: dict,
    script: dict,
    llm_router: LLMRouter,
) -> list[str]:
    """Return semantic-issue strings (empty if clean).

    Robust to LLM failure: on any exception, logs and returns []. Callers
    must treat empty list as "no signal" rather than "validated clean".
    """
    # Skip if there's nothing semantic to compare — at minimum we need
    # endings (the artifact most prone to contradicting events).
    has_events = bool((world.get("events_data") or []) or (script.get("events_data") or []))
    has_endings = bool(script.get("endings_data"))
    if not has_endings or not has_events:
        return []

    user_message = _build_user_message(world, script)

    raw_text = ""
    try:
        async for ev in llm_router.stream_json(
            messages=[{"role": "user", "content": user_message}],
            system=_SYSTEM_PROMPT,
            max_tokens=1024,
        ):
            if ev.get("type") == "text_delta":
                raw_text += ev.get("text") or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_review.llm_failed", error=str(exc))
        return []

    raw_text = raw_text.strip()
    if not raw_text:
        return []

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        # Some providers wrap JSON in ```json fences or prefix narration.
        # Best-effort: find the first { ... } block.
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            logger.warning("semantic_review.parse_failed", sample=raw_text[:200])
            return []
        try:
            payload = json.loads(raw_text[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("semantic_review.parse_failed", sample=raw_text[:200])
            return []

    issues = payload.get("issues") if isinstance(payload, dict) else None
    if not isinstance(issues, list):
        return []
    return [str(i).strip() for i in issues if str(i).strip()]


__all__ = ["check_semantic_consistency"]
