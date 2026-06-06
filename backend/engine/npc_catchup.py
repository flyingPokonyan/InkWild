"""NPC catch-up call — runtime v2 §7.2.

When an NPC re-enters ``active_npcs`` after being off-stage for several
rounds, we run a one-shot LLM call to update their L3 inner state (intent
progress, mood shift, knowledge acquired) so the action call that follows
has accurate inner state rather than the stale snapshot from their last
active round.

Output is a single JSON object (not tool_use) — minimum plumbing, single
LLM call per NPC. Failures fall back to "use last L3 snapshot + warn":
the turn continues with stale inner state rather than blocking.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import AsyncIterator

import structlog

from engine.prompts import build_npc_catchup_system
from llm.router import LLMRouter

logger = structlog.get_logger()


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class CatchupResult:
    npc_name: str
    what_i_did_offstage: str = ""
    intent_update: dict | None = None
    mood_shift: dict | None = None
    knowledge_acquired: list[dict] = None  # type: ignore[assignment]
    usage: dict | None = None
    ok: bool = False

    def __post_init__(self) -> None:
        if self.knowledge_acquired is None:
            self.knowledge_acquired = []


def _extract_json(text: str) -> dict | None:
    """Tolerant JSON extraction — strips fences, reasoning tags, leading text."""
    if not text:
        return None
    # Strip <think>/<reasoning> blocks (same pattern as director).
    cleaned = re.sub(
        r"<(think|reasoning|thinking)\b[^>]*>.*?</\1>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    m = _JSON_OBJECT_RE.search(cleaned)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        try:
            obj, _ = json.JSONDecoder().raw_decode(cleaned)
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None


async def run_catchup(
    *,
    llm_router: LLMRouter,
    npc_name: str,
    npc_personality: str,
    npc_secret: str | None,
    last_active_round: int,
    current_round: int,
    last_intent: dict | None,
    offstage_log: list[dict],
) -> CatchupResult:
    """Run a single catch-up call for one NPC.

    Cheap by design — single thinking-tier call, no tool plumbing.
    """
    system = build_npc_catchup_system(
        npc_name=npc_name,
        npc_personality=npc_personality,
        npc_secret=npc_secret,
        last_active_round=last_active_round,
        current_round=current_round,
        last_intent=last_intent,
        offstage_log=offstage_log or [],
    )
    user = (
        f"请基于上面的上下文回答你（{npc_name}）这段时间发生了什么、"
        "你的内心状态有什么变化。只输出一个 JSON 对象，不要任何前导文字。"
    )
    text_parts: list[str] = []
    usage_data: dict | None = None

    stream: AsyncIterator[dict]
    try:
        stream = llm_router.stream_json(
            messages=[{"role": "user", "content": user}],
            system=system,
            max_tokens=1024,
        )
        async for event in stream:
            if event["type"] == "text_delta":
                text_parts.append(event.get("text", ""))
            elif event["type"] == "usage":
                usage_data = event
    except AttributeError:
        # Router without stream_json — fall back to stream_with_tools.
        try:
            async for event in llm_router.stream_with_tools(
                messages=[{"role": "user", "content": user}],
                tools=[],
                system=system,
            ):
                if event["type"] == "text_delta":
                    text_parts.append(event.get("text", ""))
                elif event["type"] == "usage":
                    usage_data = event
        except Exception as exc:  # noqa: BLE001
            logger.warning("npc_catchup.stream_failed", npc=npc_name, error=str(exc))
            return CatchupResult(npc_name=npc_name, usage=usage_data, ok=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("npc_catchup.stream_failed", npc=npc_name, error=str(exc))
        return CatchupResult(npc_name=npc_name, usage=usage_data, ok=False)

    payload = _extract_json("".join(text_parts))
    if not isinstance(payload, dict):
        logger.warning(
            "npc_catchup.parse_failed",
            npc=npc_name,
            preview="".join(text_parts)[:200],
        )
        return CatchupResult(npc_name=npc_name, usage=usage_data, ok=False)

    what = str(payload.get("what_i_did_offstage") or "").strip()[:120]
    intent_update_raw = payload.get("intent_update")
    intent_update = intent_update_raw if isinstance(intent_update_raw, dict) else None
    mood_shift_raw = payload.get("mood_shift")
    mood_shift = mood_shift_raw if isinstance(mood_shift_raw, dict) else None
    knowledge_acquired_raw = payload.get("knowledge_acquired") or []
    knowledge_acquired: list[dict] = []
    if isinstance(knowledge_acquired_raw, list):
        for entry in knowledge_acquired_raw[:5]:
            if isinstance(entry, dict):
                content = str(entry.get("content") or "").strip()[:100]
                source = str(entry.get("source") or "").strip()[:40]
                if content:
                    knowledge_acquired.append({"content": content, "source": source})

    return CatchupResult(
        npc_name=npc_name,
        what_i_did_offstage=what,
        intent_update=intent_update,
        mood_shift=mood_shift,
        knowledge_acquired=knowledge_acquired,
        usage=usage_data,
        ok=True,
    )


def apply_catchup_to_state(
    state,  # GameState (avoid circular import)
    result: CatchupResult,
) -> list[dict]:
    """Apply a catch-up result to game_state.

    Mutates ``state`` in-place. Returns memory entries that the orchestrator
    should batch-write to ``memory_entries`` (with session_id filled in
    by caller).
    """
    if not result.ok:
        return []

    # Intent update: if pivot → swap goal, stage=0; otherwise advance plan_stage.
    intent = state.npc_intents.get(result.npc_name)
    if isinstance(intent, dict) and result.intent_update:
        progress = str(result.intent_update.get("progress") or "").strip()
        delta_raw = result.intent_update.get("stage_index_delta", 1)
        try:
            delta = int(delta_raw)
        except (TypeError, ValueError):
            delta = 1
        delta = max(0, min(2, delta))
        if progress == "advance":
            stages = intent.get("plan_stages") or []
            max_stage = max(0, len(stages) - 1)
            intent["plan_stage"] = min(max_stage, int(intent.get("plan_stage") or 0) + delta)
        elif progress == "stuck":
            blocked = str(result.intent_update.get("blocked_by") or "").strip()
            if blocked:
                intent["blocked_by"] = blocked
        elif progress == "pivot":
            new_goal = str(result.intent_update.get("new_goal") or "").strip()
            if new_goal:
                intent["current_goal"] = new_goal
                intent["plan_stage"] = 0
                intent["blocked_by"] = None
        elif progress == "complete":
            intent["plan_stage"] = max(0, len(intent.get("plan_stages") or []) - 1)
        state.npc_intents[result.npc_name] = intent

    # Mood shift.
    if result.mood_shift:
        to_mood = str(result.mood_shift.get("to") or "").strip()
        if to_mood:
            relation = state.npc_relations.setdefault(
                result.npc_name,
                {"trust": 3, "mood": "正常", "last_interaction": ""},
            )
            relation["mood"] = to_mood

    # Clear offstage log on successful catch-up — knowledge has been
    # consumed into memory, no need to keep replaying it.
    if result.npc_name in state.offstage_event_log:
        state.offstage_event_log[result.npc_name] = []

    entries: list[dict] = []
    round_number = state.round_number
    for k in result.knowledge_acquired:
        entries.append(
            {
                "memory_type": "catchup_knowledge",
                "content": k["content"],
                "round_number": round_number,
                "importance": 5,
                "related_npc": result.npc_name,
            }
        )
    if result.what_i_did_offstage:
        entries.append(
            {
                "memory_type": "catchup_summary",
                "content": result.what_i_did_offstage,
                "round_number": round_number,
                "importance": 5,
                "related_npc": result.npc_name,
            }
        )
    return entries


__all__ = ["CatchupResult", "run_catchup", "apply_catchup_to_state"]
