"""Phase 1.A.5 — NPC agent uses dedicated llm router (cheap-tier slot)."""
from __future__ import annotations

import pytest

from engine.director_agent import DirectorResult
from engine.npc_agent import NPCAgent, NPCResult
from engine.orchestrator import Orchestrator
from engine.state_manager import GameState


class TaggedRouter:
    """Records which router serviced each call so we can verify slot wiring."""

    def __init__(self, tag: str, events: list[dict]):
        self.tag = tag
        self.events = events
        self.calls: list[dict] = []

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048, **kwargs):
        self.calls.append({"messages": messages, "tools": tools, "system": system})
        for event in self.events:
            yield event


class FakeDirectorAgent:
    def __init__(self, result: DirectorResult):
        self.result = result

    async def run(self, **kwargs):
        return self.result


class FakeNarratorAgent:
    async def stream(self, **kwargs):
        yield {"type": "text_delta", "text": "你走向前。"}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}


def _state() -> GameState:
    return GameState(
        current_time="第1天·上午",
        current_location="镇口",
        player_inventory=[],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        time_index=0,
    )


def _world() -> dict:
    return {
        "base_setting": "舞台。",
        "script_setting": "",
        "npc_descriptions": "王福：忠厚。",
        "ending_conditions": "",
        "npcs": [{"name": "王福", "personality": "忠厚", "secret": ""}],
        "events": [],
        "endings": [],
    }


@pytest.mark.asyncio
async def test_npc_agent_uses_dedicated_router_when_provided():
    main_router = TaggedRouter("main", events=[])
    npc_router = TaggedRouter(
        "npc",
        events=[
            {"type": "text_delta", "text": "王福：好。"},
            {"type": "usage", "input_tokens": 1, "output_tokens": 1},
        ],
    )
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=["王福"],
            npc_instructions={"王福": "回应"},
            scene_direction="风起",
            state_updates={},
            quick_actions=[],
            usage=None,
        )
    )
    orchestrator = Orchestrator(
        llm_router=main_router,
        npc_llm_router=npc_router,
        director_agent=director,
        npc_agent=NPCAgent(npc_router),
        narrator_agent=FakeNarratorAgent(),
    )

    async for _ in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        game_mode="script",
    ):
        pass

    # NPC routing landed on the cheap slot, not on game_main.
    assert len(npc_router.calls) >= 1
    assert main_router.calls == []


@pytest.mark.asyncio
async def test_default_npc_agent_falls_back_to_main_router():
    """If npc_llm_router is omitted, NPCAgent must reuse the main router."""
    main_router = TaggedRouter(
        "main",
        events=[
            {"type": "text_delta", "text": "王福：好。"},
            {"type": "usage", "input_tokens": 1, "output_tokens": 1},
        ],
    )
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=["王福"],
            npc_instructions={"王福": "回应"},
            scene_direction="风起",
            state_updates={},
            quick_actions=[],
            usage=None,
        )
    )
    orchestrator = Orchestrator(
        llm_router=main_router,
        director_agent=director,
        narrator_agent=FakeNarratorAgent(),
    )

    async for _ in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        game_mode="script",
    ):
        pass

    # The default-built NPCAgent reused main_router (no separate slot bound).
    assert orchestrator.npc_llm_router is main_router
    assert orchestrator.npc_agent.llm_router is main_router
    assert any(call for call in main_router.calls)
