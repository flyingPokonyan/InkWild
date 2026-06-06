"""Phase 0.A.3 余项 — Director can explicitly write into a specific NPC's
private memory via the ``inform_npc_calls`` tool field. Used when an NPC
should know something that the natural scene flow wouldn't deliver (e.g.
something happened off-screen, someone whispered to them).
"""
from __future__ import annotations

import pytest

from engine.director_agent import DirectorResult
from engine.npc_agent import NPCResult
from engine.orchestrator import Orchestrator
from engine.state_manager import GameState


class FakeDirectorAgent:
    def __init__(self, result: DirectorResult):
        self.result = result

    async def run(self, **kwargs):
        return self.result


class FakeNPCAgent:
    async def run(self, **kwargs):
        return NPCResult(npc_name=kwargs["npc_name"], dialogue=f"{kwargs['npc_name']}: ...")


class FakeNarratorAgent:
    async def stream(self, **kwargs):
        yield {"type": "text_delta", "text": "夜色降临。"}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}

    async def stream_prelude(self, **kwargs):
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}


def _state() -> GameState:
    return GameState(
        current_time="第1天·夜晚",
        current_location="后院",
        player_inventory=[],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        time_index=0,
    )


def _world() -> dict:
    return {
        "base_setting": "民国小镇。",
        "script_setting": "",
        "npc_descriptions": "王福：忠厚。\n赵姐：热心。",
        "ending_conditions": "",
        "npcs": [
            {"name": "王福", "personality": "忠厚", "secret": ""},
            {"name": "赵姐", "personality": "热心", "secret": ""},
        ],
        "events": [],
        "endings": [],
    }


def _build(director_result: DirectorResult) -> Orchestrator:
    return Orchestrator(
        llm_router=object(),
        director_agent=FakeDirectorAgent(director_result),
        npc_agent=FakeNPCAgent(),
        narrator_agent=FakeNarratorAgent(),
    )


@pytest.mark.asyncio
async def test_director_inform_npc_calls_write_to_dual_memory_entries():
    director_result = DirectorResult(
        involved_npcs=["王福"],
        npc_instructions={"王福": "回应"},
        scene_direction="后院起风。",
        state_updates={},
        quick_actions=[],
        inform_npc_calls=[
            {"npc": "赵姐", "info": "李大夫今早离镇了。", "importance": "high"},
        ],
    )
    orchestrator = _build(director_result)

    done_event = None
    async for event in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        game_mode="script",
        session_id="sess-1",
        round_number=3,
    ):
        if event.get("type") == "done":
            done_event = event

    assert done_event is not None
    entries = done_event["dual_memory_entries"]
    director_told = [e for e in entries if e.get("memory_type") == "director_told"]
    assert len(director_told) == 1
    entry = director_told[0]
    assert entry["related_npc"] == "赵姐"
    assert entry["content"] == "李大夫今早离镇了。"
    assert entry["round_number"] == 3
    assert entry["session_id"] == "sess-1"
    # high → importance 8
    assert entry["importance"] == 8


@pytest.mark.asyncio
async def test_director_inform_npc_rejects_unknown_npc(caplog):
    director_result = DirectorResult(
        involved_npcs=[],
        npc_instructions={},
        scene_direction="什么也没发生。",
        state_updates={},
        quick_actions=[],
        inform_npc_calls=[
            {"npc": "幽灵 NPC", "info": "本应被忽略", "importance": "high"},
            {"npc": "王福", "info": "本应被接受", "importance": "medium"},
        ],
    )
    orchestrator = _build(director_result)

    done_event = None
    async for event in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        game_mode="script",
        session_id="sess-1",
        round_number=1,
    ):
        if event.get("type") == "done":
            done_event = event

    director_told = [
        e for e in done_event["dual_memory_entries"] if e.get("memory_type") == "director_told"
    ]
    # 只有真实存在的 NPC 被采纳。
    assert len(director_told) == 1
    assert director_told[0]["related_npc"] == "王福"
    # medium → 5
    assert director_told[0]["importance"] == 5


@pytest.mark.asyncio
async def test_director_inform_npc_skips_blank_calls():
    director_result = DirectorResult(
        involved_npcs=[],
        npc_instructions={},
        scene_direction="...",
        state_updates={},
        quick_actions=[],
        inform_npc_calls=[
            {"npc": "", "info": "无人收"},
            {"npc": "王福", "info": ""},
            {"npc": "赵姐", "info": "  "},
        ],
    )
    orchestrator = _build(director_result)
    done_event = None
    async for event in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        game_mode="script",
        session_id="sess-1",
        round_number=1,
    ):
        if event.get("type") == "done":
            done_event = event

    director_told = [
        e for e in done_event["dual_memory_entries"] if e.get("memory_type") == "director_told"
    ]
    assert director_told == []


def test_director_agent_coerces_inform_npc_calls():
    """Coerce ignores malformed entries and normalizes importance."""
    from engine.director_agent import DirectorAgent

    raw = [
        {"npc": "王福", "info": "OK", "importance": "MEDIUM"},
        {"npc": "  ", "info": "blank npc"},
        {"npc": "赵姐", "info": "  "},  # blank info
        "not a dict",
        {"npc": "李掌柜", "info": "默认 importance"},
    ]
    cleaned = DirectorAgent._coerce_inform_npc_calls(raw)
    assert cleaned == [
        {"npc": "王福", "info": "OK", "importance": "medium"},
        {"npc": "李掌柜", "info": "默认 importance", "importance": "high"},
    ]
