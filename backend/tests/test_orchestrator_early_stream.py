"""Phase 1.A.1 — Narrator early streaming runs in parallel with NPC tasks."""
from __future__ import annotations

import asyncio
import time

import pytest

from config import settings
from engine.director_agent import DirectorResult
from engine.npc_agent import NPCResult
from engine.orchestrator import Orchestrator
from engine.state_manager import GameState


class FakeDirectorAgent:
    def __init__(self, result: DirectorResult):
        self.result = result

    async def run(self, **kwargs):
        return self.result


class SlowNPCAgent:
    """Simulates a slow NPC agent so we can observe parallelism."""

    def __init__(self, delay_seconds: float):
        self.delay_seconds = delay_seconds
        self.start_time: float | None = None
        self.end_time: float | None = None

    async def run(self, **kwargs):
        if self.start_time is None:
            self.start_time = time.perf_counter()
        await asyncio.sleep(self.delay_seconds)
        self.end_time = time.perf_counter()
        return NPCResult(npc_name=kwargs["npc_name"], dialogue=f'{kwargs["npc_name"]}: 嗯。')


class RecordingNarratorAgent:
    def __init__(self):
        self.prelude_calls: list[dict] = []
        self.stream_calls: list[dict] = []
        self.prelude_started_at: float | None = None
        self.prelude_finished_at: float | None = None

    async def stream_prelude(self, **kwargs):
        self.prelude_calls.append(kwargs)
        self.prelude_started_at = time.perf_counter()
        # Two-token prelude with a tiny pause to simulate streaming.
        for token in ["镇口", "起了风。"]:
            await asyncio.sleep(0.01)
            yield {"type": "text_delta", "text": token}
        yield {"type": "usage", "input_tokens": 50, "output_tokens": 20}
        self.prelude_finished_at = time.perf_counter()

    async def stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        for token in ["王福开口：", "「来了。」"]:
            yield {"type": "text_delta", "text": token}
        yield {"type": "usage", "input_tokens": 100, "output_tokens": 40}


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


def _build_orchestrator(narrator: RecordingNarratorAgent, npc_agent: SlowNPCAgent) -> Orchestrator:
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=["王福"],
            npc_instructions={"王福": "回应"},
            scene_direction="风起。",
            state_updates={},
            quick_actions=["继续"],
            usage=None,
        )
    )
    return Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=npc_agent,
        narrator_agent=narrator,
    )


@pytest.mark.asyncio
async def test_early_stream_yields_prelude_tokens_before_npc_finishes(monkeypatch):
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", True)
    npc = SlowNPCAgent(delay_seconds=0.15)
    narrator = RecordingNarratorAgent()
    orchestrator = _build_orchestrator(narrator, npc)

    first_narrative_time: float | None = None
    npc_done_time: float | None = None

    async for event in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        game_mode="script",
    ):
        if event.get("type") == "narrative" and first_narrative_time is None:
            first_narrative_time = time.perf_counter()
        # NPC completion observable through narrator.stream call (it requires npc_dialogues)
        if narrator.stream_calls and npc_done_time is None and npc.end_time is not None:
            npc_done_time = npc.end_time

    assert first_narrative_time is not None
    assert npc.end_time is not None
    # The first narrative token must arrive BEFORE the NPC finishes — that's
    # the whole point of early streaming.
    assert first_narrative_time < npc.end_time, (
        f"first narrative={first_narrative_time}, npc done={npc.end_time}"
    )


@pytest.mark.asyncio
async def test_early_stream_passes_prelude_text_to_weave(monkeypatch):
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", True)
    narrator = RecordingNarratorAgent()
    orchestrator = _build_orchestrator(narrator, SlowNPCAgent(delay_seconds=0.01))

    async for _ in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        game_mode="script",
    ):
        pass

    # Prelude ran exactly once; weave received the prelude text for continuity.
    assert len(narrator.prelude_calls) == 1
    assert len(narrator.stream_calls) == 1
    weave_kwargs = narrator.stream_calls[0]
    assert weave_kwargs.get("prelude_text") == "镇口起了风。"


@pytest.mark.asyncio
async def test_early_stream_disabled_keeps_legacy_sequential_behavior(monkeypatch):
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", False)
    narrator = RecordingNarratorAgent()
    orchestrator = _build_orchestrator(narrator, SlowNPCAgent(delay_seconds=0.01))

    events: list[dict] = []
    async for event in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        game_mode="script",
    ):
        events.append(event)

    # Legacy path: no prelude call, no prelude_text in weave, and the
    # post-NPC "thinking" hint is restored.
    assert narrator.prelude_calls == []
    assert narrator.stream_calls[0].get("prelude_text") is None
    processing_phases = [e["phase"] for e in events if e.get("type") == "processing"]
    assert "thinking" in processing_phases


@pytest.mark.asyncio
async def test_done_event_usage_merges_prelude_and_weave_tokens(monkeypatch):
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", True)
    narrator = RecordingNarratorAgent()
    orchestrator = _build_orchestrator(narrator, SlowNPCAgent(delay_seconds=0.01))

    done_event: dict | None = None
    async for event in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        game_mode="script",
    ):
        if event.get("type") == "done":
            done_event = event

    assert done_event is not None
    usage = done_event["usage"]
    # Prelude (50/20) + weave (100/40) summed.
    assert usage["input_tokens"] == 150
    assert usage["output_tokens"] == 60
