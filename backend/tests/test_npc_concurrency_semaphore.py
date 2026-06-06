"""Phase 2.D.3 — orchestrator caps concurrent NPC LLM calls per turn."""
from __future__ import annotations

import asyncio

import pytest

from config import settings
from engine.director_agent import DirectorResult
from engine.npc_agent import NPCResult
from engine.orchestrator import Orchestrator
from engine.state_manager import GameState


class TrackingNPCAgent:
    """Records peak in-flight count to verify the semaphore takes effect."""

    def __init__(self, hold_seconds: float = 0.05):
        self.hold_seconds = hold_seconds
        self.in_flight = 0
        self.peak = 0
        self._lock = asyncio.Lock()

    async def run(self, **kwargs):
        async with self._lock:
            self.in_flight += 1
            if self.in_flight > self.peak:
                self.peak = self.in_flight
        try:
            await asyncio.sleep(self.hold_seconds)
        finally:
            async with self._lock:
                self.in_flight -= 1
        return NPCResult(npc_name=kwargs["npc_name"], dialogue=f"{kwargs['npc_name']}: ok")


class FakeNarratorAgent:
    async def stream(self, **kwargs):
        yield {"type": "text_delta", "text": "..."}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}

    async def stream_prelude(self, **kwargs):
        yield {"type": "usage", "input_tokens": 0, "output_tokens": 0}


class FakeDirectorAgent:
    def __init__(self, npcs: list[str]):
        self.npcs = npcs

    async def run(self, **kwargs):
        return DirectorResult(
            involved_npcs=self.npcs,
            npc_instructions={n: "回应" for n in self.npcs},
            scene_direction="...",
            state_updates={},
            quick_actions=[],
        )


def _state() -> GameState:
    return GameState(
        current_time="第1天·上午",
        current_location="广场",
        player_inventory=[],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        time_index=0,
    )


def _world(npc_names: list[str]) -> dict:
    return {
        "base_setting": "舞台。",
        "script_setting": "",
        "npc_descriptions": "",
        "ending_conditions": "",
        "npcs": [{"name": n, "personality": "x", "secret": ""} for n in npc_names],
        "events": [],
        "endings": [],
    }


@pytest.mark.asyncio
async def test_npc_concurrency_capped_at_max(monkeypatch):
    # Semaphore only matters in parallel mode; force-disable sequential.
    monkeypatch.setattr(settings, "npc_dialogue_sequential_enabled", False)
    monkeypatch.setattr(settings, "npc_max_concurrency", 3)
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", False)
    npcs = ["A", "B", "C", "D", "E", "F", "G"]
    tracker = TrackingNPCAgent(hold_seconds=0.05)
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=FakeDirectorAgent(npcs),
        npc_agent=tracker,
        narrator_agent=FakeNarratorAgent(),
    )

    async for _ in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(npcs),
        game_mode="script",
    ):
        pass

    assert tracker.peak <= 3, f"peak in-flight was {tracker.peak}, expected ≤ 3"
    # And we did actually run all NPCs.
    assert tracker.in_flight == 0


@pytest.mark.asyncio
async def test_npc_concurrency_default_allows_all_when_below_cap(monkeypatch):
    monkeypatch.setattr(settings, "npc_dialogue_sequential_enabled", False)
    monkeypatch.setattr(settings, "npc_max_concurrency", 6)
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", False)
    npcs = ["A", "B", "C"]
    tracker = TrackingNPCAgent(hold_seconds=0.02)
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=FakeDirectorAgent(npcs),
        npc_agent=tracker,
        narrator_agent=FakeNarratorAgent(),
    )

    async for _ in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(npcs),
        game_mode="script",
    ):
        pass

    assert tracker.peak == 3
