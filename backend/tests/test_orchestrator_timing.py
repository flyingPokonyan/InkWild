"""Phase 1.A.6 — assert orchestrator emits stage timing logs and SSE phase events."""
from __future__ import annotations

import pytest
from structlog.testing import capture_logs

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
        return NPCResult(npc_name=kwargs["npc_name"], dialogue=f'{kwargs["npc_name"]}: 嗯。')


class FakeNarratorAgent:
    def __init__(self, deltas: list[str], prelude_deltas: list[str] | None = None):
        self.deltas = deltas
        self.prelude_deltas = prelude_deltas or []

    async def stream(self, **kwargs):
        for delta in self.deltas:
            yield {"type": "text_delta", "text": delta}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}

    async def stream_prelude(self, **kwargs):
        for delta in self.prelude_deltas:
            yield {"type": "text_delta", "text": delta}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}


def _make_state() -> GameState:
    return GameState(
        current_time="第1天·上午",
        current_location="镇口",
        player_inventory=[],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        time_index=0,
    )


def _make_world_data() -> dict:
    return {
        "base_setting": "舞台。",
        "script_setting": "",
        "npc_descriptions": "王福：忠厚。",
        "ending_conditions": "",
        "npcs": [{"name": "王福", "personality": "忠厚", "secret": ""}],
        "events": [],
        "endings": [],
    }


def _build_orchestrator(involved_npcs: list[str]) -> Orchestrator:
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=involved_npcs,
            npc_instructions={name: "回应玩家" for name in involved_npcs},
            scene_direction="风起。",
            state_updates={},
            quick_actions=["继续观察"],
            usage=None,
        )
    )
    return Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=FakeNPCAgent(),
        narrator_agent=FakeNarratorAgent(deltas=["你走向前。"]),
    )


@pytest.mark.asyncio
async def test_orchestrator_emits_all_stage_timing_logs():
    orchestrator = _build_orchestrator(["王福"])
    with capture_logs() as logs:
        async for _event in orchestrator.process_action(
            action_text="我观察",
            game_state=_make_state(),
            recent_messages=[],
            context_summary=None,
            world_data=_make_world_data(),
            game_mode="script",
        ):
            pass

    timing_stages = [
        log["stage"] for log in logs if log.get("event") == "stage.timing"
    ]
    expected = {
        "moderation_input",
        "world_tick",
        "director",
        "narrator_first_token",
        "narrator",
        "moderation_output",
        "turn_total",
    }
    actual = set(timing_stages)
    assert expected.issubset(actual)
    # NPC dialogue stage is named after the active mode (sequential default,
    # parallel under the legacy flag); we accept either so this test stays
    # mode-agnostic.
    assert {"npc_sequential", "npc_parallel"} & actual
    for log in logs:
        if log.get("event") == "stage.timing":
            assert log.get("duration_ms") is not None
            assert log["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_orchestrator_emits_directing_phase_before_director_runs():
    orchestrator = _build_orchestrator(["王福"])
    events = []
    async for event in orchestrator.process_action(
        action_text="我观察",
        game_state=_make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_make_world_data(),
        game_mode="script",
    ):
        events.append(event)

    processing_phases = [event["phase"] for event in events if event.get("type") == "processing"]
    # directing fires before the Director call. With early-stream mode (default
    # ON) the post-NPC "thinking" hint is suppressed because the prelude
    # already produces visible tokens.
    assert processing_phases[0] == "directing"


@pytest.mark.asyncio
async def test_orchestrator_skips_npc_parallel_timing_when_no_npcs():
    orchestrator = _build_orchestrator([])
    with capture_logs() as logs:
        async for _event in orchestrator.process_action(
            action_text="我观察四周",
            game_state=_make_state(),
            recent_messages=[],
            context_summary=None,
            world_data=_make_world_data(),
            game_mode="free",
        ):
            pass

    timing_stages = [
        log["stage"] for log in logs if log.get("event") == "stage.timing"
    ]
    assert "npc_parallel" not in timing_stages
    assert "narrator" in timing_stages
    assert "turn_total" in timing_stages
