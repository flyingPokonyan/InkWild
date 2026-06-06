"""NPC-1 — sequential NPC dialogue inside a single turn.

Director.npc_speech_order picks the order, each later speaker receives
``peer_dialogues_so_far`` containing earlier speakers' lines, the orchestrator
caps the speaker count to ``settings.npc_max_speakers_per_turn``, and the flag
``settings.npc_dialogue_sequential_enabled`` falls back to legacy parallel
when off.
"""
from __future__ import annotations

import asyncio

import pytest

from config import settings
from engine.director_agent import DirectorAgent, DirectorResult
from engine.npc_agent import NPCResult
from engine.orchestrator import Orchestrator
from engine.state_manager import GameState


class RecordingNPCAgent:
    """Captures call order, kwargs, and tracks peak in-flight."""

    def __init__(self, hold_seconds: float = 0.02):
        self.hold_seconds = hold_seconds
        self.calls: list[dict] = []
        self.in_flight = 0
        self.peak = 0
        self._lock = asyncio.Lock()

    async def run(self, **kwargs):
        async with self._lock:
            self.in_flight += 1
            if self.in_flight > self.peak:
                self.peak = self.in_flight
        self.calls.append({
            "npc_name": kwargs["npc_name"],
            "peer_dialogues_so_far": list(kwargs.get("peer_dialogues_so_far") or []),
        })
        try:
            await asyncio.sleep(self.hold_seconds)
        finally:
            async with self._lock:
                self.in_flight -= 1
        return NPCResult(
            npc_name=kwargs["npc_name"],
            dialogue=f"{kwargs['npc_name']} 说话",
        )


class FakeDirectorAgent:
    def __init__(self, result: DirectorResult):
        self.result = result

    async def run(self, **kwargs):
        return self.result


class FakeNarratorAgent:
    async def stream(self, **kwargs):
        yield {"type": "text_delta", "text": "..."}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}

    async def stream_prelude(self, **kwargs):
        yield {"type": "usage", "input_tokens": 0, "output_tokens": 0}


def _state() -> GameState:
    return GameState(
        current_time="第1天·上午",
        current_location="茶摊",
        player_inventory=[],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        time_index=0,
    )


def _world(npc_names: list[str]) -> dict:
    return {
        "base_setting": "民国小镇。",
        "script_setting": "",
        "npc_descriptions": "",
        "ending_conditions": "",
        "npcs": [
            {"name": n, "personality": "x", "secret": ""} for n in npc_names
        ],
        "events": [],
        "endings": [],
    }


async def _drive(orchestrator: Orchestrator, npc_names: list[str]) -> None:
    async for _ in orchestrator.process_action(
        action_text="我观察",
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(npc_names),
        game_mode="script",
    ):
        pass


@pytest.mark.asyncio
async def test_director_speech_order_drives_npc_call_order(monkeypatch):
    monkeypatch.setattr(settings, "npc_dialogue_sequential_enabled", True)
    monkeypatch.setattr(settings, "npc_max_speakers_per_turn", 5)
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", False)

    director_result = DirectorResult(
        involved_npcs=["王福", "赵姐", "李掌柜"],
        npc_instructions={n: "回应" for n in ["王福", "赵姐", "李掌柜"]},
        scene_direction="...",
        state_updates={},
        quick_actions=[],
        npc_speech_order=["赵姐", "王福", "李掌柜"],
    )
    npc_agent = RecordingNPCAgent()
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=FakeDirectorAgent(director_result),
        npc_agent=npc_agent,
        narrator_agent=FakeNarratorAgent(),
    )

    await _drive(orchestrator, ["王福", "赵姐", "李掌柜"])

    assert [c["npc_name"] for c in npc_agent.calls] == ["赵姐", "王福", "李掌柜"]


@pytest.mark.asyncio
async def test_later_speaker_sees_earlier_dialogue(monkeypatch):
    monkeypatch.setattr(settings, "npc_dialogue_sequential_enabled", True)
    monkeypatch.setattr(settings, "npc_max_speakers_per_turn", 5)
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", False)

    director_result = DirectorResult(
        involved_npcs=["A", "B", "C"],
        npc_instructions={"A": ".", "B": ".", "C": "."},
        scene_direction="...",
        state_updates={},
        quick_actions=[],
        npc_speech_order=["A", "B", "C"],
    )
    npc_agent = RecordingNPCAgent()
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=FakeDirectorAgent(director_result),
        npc_agent=npc_agent,
        narrator_agent=FakeNarratorAgent(),
    )

    await _drive(orchestrator, ["A", "B", "C"])

    # First speaker: empty peer history.
    assert npc_agent.calls[0]["peer_dialogues_so_far"] == []
    # Second speaker: sees A's line.
    assert npc_agent.calls[1]["peer_dialogues_so_far"] == [
        {"npc_name": "A", "dialogue": "A 说话"},
    ]
    # Third speaker: sees A and B.
    assert npc_agent.calls[2]["peer_dialogues_so_far"] == [
        {"npc_name": "A", "dialogue": "A 说话"},
        {"npc_name": "B", "dialogue": "B 说话"},
    ]


@pytest.mark.asyncio
async def test_sequential_mode_peak_inflight_is_one(monkeypatch):
    monkeypatch.setattr(settings, "npc_dialogue_sequential_enabled", True)
    monkeypatch.setattr(settings, "npc_max_speakers_per_turn", 5)
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", False)

    director_result = DirectorResult(
        involved_npcs=["A", "B", "C", "D"],
        npc_instructions={n: "." for n in ["A", "B", "C", "D"]},
        scene_direction="...",
        state_updates={},
        quick_actions=[],
        npc_speech_order=[],
    )
    npc_agent = RecordingNPCAgent(hold_seconds=0.02)
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=FakeDirectorAgent(director_result),
        npc_agent=npc_agent,
        narrator_agent=FakeNarratorAgent(),
    )

    await _drive(orchestrator, ["A", "B", "C", "D"])

    assert npc_agent.peak == 1, f"sequential mode should serialize, peak={npc_agent.peak}"


@pytest.mark.asyncio
async def test_max_speakers_per_turn_caps_speaker_count(monkeypatch):
    monkeypatch.setattr(settings, "npc_dialogue_sequential_enabled", True)
    monkeypatch.setattr(settings, "npc_max_speakers_per_turn", 2)
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", False)

    director_result = DirectorResult(
        involved_npcs=["A", "B", "C", "D", "E"],
        npc_instructions={n: "." for n in ["A", "B", "C", "D", "E"]},
        scene_direction="...",
        state_updates={},
        quick_actions=[],
        npc_speech_order=["B", "A", "C", "D", "E"],
    )
    npc_agent = RecordingNPCAgent()
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=FakeDirectorAgent(director_result),
        npc_agent=npc_agent,
        narrator_agent=FakeNarratorAgent(),
    )

    await _drive(orchestrator, ["A", "B", "C", "D", "E"])

    # Only the first 2 from speech_order speak.
    assert [c["npc_name"] for c in npc_agent.calls] == ["B", "A"]


@pytest.mark.asyncio
async def test_flag_disabled_falls_back_to_parallel(monkeypatch):
    monkeypatch.setattr(settings, "npc_dialogue_sequential_enabled", False)
    monkeypatch.setattr(settings, "npc_max_concurrency", 6)
    monkeypatch.setattr(settings, "narrator_early_stream_enabled", False)

    director_result = DirectorResult(
        involved_npcs=["A", "B", "C"],
        npc_instructions={n: "." for n in ["A", "B", "C"]},
        scene_direction="...",
        state_updates={},
        quick_actions=[],
        npc_speech_order=["C", "B", "A"],  # ignored in parallel mode
    )
    npc_agent = RecordingNPCAgent(hold_seconds=0.05)
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=FakeDirectorAgent(director_result),
        npc_agent=npc_agent,
        narrator_agent=FakeNarratorAgent(),
    )

    await _drive(orchestrator, ["A", "B", "C"])

    # Parallel mode: peer_dialogues_so_far should be empty/None for every NPC.
    for call in npc_agent.calls:
        assert call["peer_dialogues_so_far"] == []
    # And concurrency should exceed 1.
    assert npc_agent.peak == 3


def test_coerce_speech_order_filters_and_dedupes():
    """Director hallucinations get dropped, dupes collapse, order preserved."""
    coerce = DirectorAgent._coerce_speech_order
    assert coerce(["B", "A", "C"], ["A", "B", "C"]) == ["B", "A", "C"]
    # Unknown name dropped.
    assert coerce(["B", "幽灵", "A"], ["A", "B"]) == ["B", "A"]
    # Duplicates collapsed to first appearance.
    assert coerce(["A", "B", "A"], ["A", "B"]) == ["A", "B"]
    # Empty/None.
    assert coerce(None, ["A"]) == []
    assert coerce([], ["A"]) == []
    # Non-list input.
    assert coerce("A,B", ["A", "B"]) == []
    # Whitespace and falsy items skipped.
    assert coerce(["  ", None, "A"], ["A"]) == ["A"]


def test_director_result_default_speech_order_is_empty():
    """Backward compatibility: callers that don't pass npc_speech_order
    still construct a valid DirectorResult."""
    result = DirectorResult(
        involved_npcs=["A"],
        npc_instructions={"A": "."},
        scene_direction="...",
        state_updates={},
        quick_actions=[],
    )
    assert result.npc_speech_order == []


def test_build_npc_system_renders_peer_dialogues():
    from engine.prompts import build_npc_system

    prompt = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚",
        npc_secret=None,
        instruction=".",
        peer_dialogues_so_far=[
            {"npc_name": "赵姐", "dialogue": "茶刚泡好。"},
            {"npc_name": "李掌柜", "dialogue": "今儿话怎么少。"},
        ],
    )
    assert "本轮其他人已经说过的话" in prompt
    assert "赵姐" in prompt and "茶刚泡好" in prompt
    assert "李掌柜" in prompt and "今儿话怎么少" in prompt


def test_build_npc_system_skips_peer_dialogues_when_empty():
    from engine.prompts import build_npc_system

    prompt = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚",
        npc_secret=None,
        instruction=".",
        peer_dialogues_so_far=None,
    )
    assert "本轮其他人已经说过的话" not in prompt

    prompt_empty_list = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚",
        npc_secret=None,
        instruction=".",
        peer_dialogues_so_far=[],
    )
    assert "本轮其他人已经说过的话" not in prompt_empty_list
