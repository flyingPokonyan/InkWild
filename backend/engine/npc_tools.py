"""NPC-side tools — runtime v2 §6.

Four cheap (sub-100ms, non-LLM) lookup tools the NPC agent can call before
emitting its final action. Tools matter because they restore the "I checked
my notes before answering" feel that makes the NPC look like an agent and
not a one-shot generator. Costly LLM-based recall lives elsewhere; these
just read game_state / world_data / memory tables.

Tool schema is intentionally narrow: query string in, terse JSON out. The
NPC LLM decides whether/when to call; orchestrator caps total calls so a
runaway loop can't blow the latency budget (§14.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from engine.memory_manager import MemoryManager
from engine.state_manager import GameState

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Tool JSON schemas (passed to LLM as tools array)
# ---------------------------------------------------------------------------

RECALL_MEMORY_NPC_TOOL = {
    "name": "recall_memory",
    "description": (
        "搜索你自己（这个 NPC）的私有记忆。当你需要回想某人/某事/某话题以前发生过什么时调用。"
        "返回最多 3 条相关记忆。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要搜索的关键词或短语（例如 NPC 名、事件、地点、话题）",
            },
        },
        "required": ["query"],
    },
}

CHECK_RELATIONSHIP_TOOL = {
    "name": "check_relationship",
    "description": (
        "查看你当前对场上某个 NPC 的态度（信任度、情绪、最近一次互动）。"
        "当你拿不准对某人是亲是疏时调用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "other_npc": {
                "type": "string",
                "description": "目标 NPC 名字",
            },
        },
        "required": ["other_npc"],
    },
}

CONSIDER_INTENT_TOOL = {
    "name": "consider_intent_progress",
    "description": (
        "查看你自己当前的目标进展（current_goal / plan_stage / blocked_by）。"
        "当你想确认「我现在最该做的事是什么」时调用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

LOOK_AT_TOOL = {
    "name": "look_at",
    "description": (
        "仔细观察场上某 NPC / 物 / 地点的细节。"
        "返回你（这个 NPC）合理能察觉到的信息——你不知道的玩家私下做的事不会出现在结果里。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "detail": {
                "type": "string",
                "description": "要观察的对象名字（NPC / 物品 / 地点）",
            },
        },
        "required": ["detail"],
    },
}

FINALIZE_ACTION_TOOL_NAME = "finalize_action"  # built dynamically per NPC


def build_finalize_action_tool(npc_action_schema: dict) -> dict:
    """Wrap NPC_ACTION_SCHEMA into a finalize-style tool the LLM uses to
    submit its decision after any number of query-tool calls."""
    return {
        "name": FINALIZE_ACTION_TOOL_NAME,
        "description": (
            "提交你这一轮最终的行动。在调用完所有查询工具后必须调用此工具一次。"
            "你只能调用一次 finalize_action；调用后表示你这轮决策完成。"
        ),
        "input_schema": npc_action_schema,
    }


def npc_query_tools() -> list[dict]:
    """Query tools advertised to the NPC LLM.

    Only the two that can surface info NOT already in the NPC's prompt:
    - ``recall_memory`` — self-chosen memory search (beyond the pre-injected
      top-N memories).
    - ``look_at`` — observe a specific NPC / item / location detail.

    ``check_relationship`` and ``consider_intent_progress`` were dropped: the
    NPC's own relations (npc_relation + peer_relations) and current_intent are
    ALREADY injected into its system prompt, so calling them just burned a
    sequential LLM round-trip to fetch data already in context. (The executor
    in ``execute_tool`` still handles them defensively if a model calls one.)
    """
    return [
        RECALL_MEMORY_NPC_TOOL,
        LOOK_AT_TOOL,
    ]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


@dataclass
class ToolContext:
    """Everything a tool handler needs to answer. Built fresh per NPC turn."""

    npc_name: str
    game_state: GameState
    world_data: dict
    session_id: str | None
    db: Any  # AsyncSession; can't import here without circular issues
    memory_manager: MemoryManager
    # Counters for cap enforcement
    tool_call_count: int = 0
    tool_results: list[dict] = field(default_factory=list)


def _terse(value: str, limit: int = 150) -> str:
    value = (value or "").strip()
    if len(value) > limit:
        value = value[:limit].rstrip() + "…"
    return value


def _format_intent(intent: dict | None) -> dict:
    if not intent:
        return {"current_goal": "（未设置）", "stage": "—"}
    stages = intent.get("plan_stages") or []
    idx = int(intent.get("plan_stage") or 0)
    stage_label = stages[idx] if 0 <= idx < len(stages) else "—"
    return {
        "current_goal": str(intent.get("current_goal") or "")[:80],
        "urgency": intent.get("urgency"),
        "stage": stage_label,
        "blocked_by": intent.get("blocked_by") or None,
    }


def _format_relationship(relation: dict | None) -> dict:
    if not relation:
        return {"trust": 3, "mood": "正常", "last_interaction": ""}
    return {
        "trust": int(relation.get("trust", 3)),
        "mood": str(relation.get("mood", "正常")),
        "last_interaction": _terse(str(relation.get("last_interaction", "")), 60),
    }


async def execute_tool(
    name: str,
    raw_input: dict,
    ctx: ToolContext,
) -> dict:
    """Dispatch one tool call. Returns a terse JSON-shaped dict; errors are
    flattened into ``{"error": "..."}`` so the LLM keeps moving.
    """
    ctx.tool_call_count += 1
    try:
        if name == RECALL_MEMORY_NPC_TOOL["name"]:
            query = str(raw_input.get("query") or "").strip()
            if not query:
                return {"error": "missing query"}
            if not ctx.session_id:
                return {"results": [], "note": "no memory backend"}
            # Always use a fresh DB session — multiple NPCs may run tools
            # in parallel under asyncio.gather, and the turn-level session
            # is being used by the prelude task. Sharing it triggers asyncpg
            # "another operation in progress".
            try:
                from database import async_session
            except Exception:  # noqa: BLE001
                return {"results": [], "note": "no db"}
            try:
                async with async_session() as tool_db:
                    hits = await ctx.memory_manager.query_npc_memories(
                        tool_db,
                        ctx.session_id,
                        ctx.npc_name,
                        limit=3,
                        query_text=query,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "npc_tool.recall_memory_failed",
                    npc=ctx.npc_name,
                    error=str(exc),
                )
                return {"error": "recall_failed"}
            return {
                "results": [
                    {
                        "round": h.get("round_number"),
                        "content": _terse(str(h.get("content") or "")),
                        "importance": h.get("importance"),
                    }
                    for h in hits
                ],
            }

        if name == CHECK_RELATIONSHIP_TOOL["name"]:
            target = str(raw_input.get("other_npc") or "").strip()
            if not target:
                return {"error": "missing other_npc"}
            relation = (ctx.game_state.npc_relations or {}).get(target)
            return {
                "target": target,
                "you_view": _format_relationship(relation),
                "note": (
                    "你不知道 TA 对你的看法，只知道你自己的态度"
                    if relation
                    else "你跟 TA 没有正式记录的关系"
                ),
            }

        if name == CONSIDER_INTENT_TOOL["name"]:
            intent = (ctx.game_state.npc_intents or {}).get(ctx.npc_name)
            return _format_intent(intent)

        if name == LOOK_AT_TOOL["name"]:
            target = str(raw_input.get("detail") or "").strip()
            if not target:
                return {"error": "missing detail"}
            # Try NPCs first.
            for npc in ctx.world_data.get("npcs") or []:
                if str(npc.get("name") or "").strip() == target:
                    visible = {
                        "name": target,
                        "personality_hint": _terse(str(npc.get("personality") or ""), 80),
                    }
                    # Never leak secret; only show schedule slot for current time.
                    slot_loc = (
                        npc.get("schedule", {}).get(_current_time_slot(ctx.game_state))
                        or npc.get("initial_location")
                        or ""
                    )
                    if slot_loc:
                        visible["likely_location"] = slot_loc
                    return visible
            # Locations.
            for loc in ctx.world_data.get("locations") or []:
                if isinstance(loc, dict) and str(loc.get("name") or "").strip() == target:
                    return {
                        "location": target,
                        "description": _terse(str(loc.get("description") or "")),
                    }
            # Items in player inventory.
            if target in (ctx.game_state.player_inventory or []):
                return {"item": target, "where": "player_inventory"}
            return {"note": f"{target} 不在你能合理观察到的范围内"}

        return {"error": f"unknown tool: {name}"}
    finally:
        ctx.tool_results.append({"tool": name, "input": raw_input})


def _current_time_slot(state: GameState) -> str:
    raw = state.current_time or ""
    if "·" in raw:
        return raw.split("·", 1)[1]
    return raw


__all__ = [
    "RECALL_MEMORY_NPC_TOOL",
    "CHECK_RELATIONSHIP_TOOL",
    "CONSIDER_INTENT_TOOL",
    "LOOK_AT_TOOL",
    "FINALIZE_ACTION_TOOL_NAME",
    "build_finalize_action_tool",
    "npc_query_tools",
    "ToolContext",
    "execute_tool",
]
