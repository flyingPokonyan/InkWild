"""Regression tests for the failure modes seen in the 2026-05-23 VPS soak:
empty JSON-mode output, multi-object 'Extra data' responses, and combined
thinking-tag + extra-data emissions.

Kept lean per the light-tests policy — three cases that pin the bug
class, not a comprehensive matrix.
"""
from __future__ import annotations

import pytest

from engine.director_agent import (
    DirectorAgent,
    DirectorParseError,
    _extract_json_from_text,
)
from engine.state_manager import GameState


def test_extract_handles_extra_data_multi_object():
    """DeepSeek V4 Pro occasionally emits two JSON objects back-to-back.
    raw_decode takes the first valid one and ignores the trailing junk.
    """
    raw = '{"npc_instructions": {}, "quick_actions": ["a"]} {"orphan": "x"}'
    assert _extract_json_from_text(raw) == {
        "npc_instructions": {},
        "quick_actions": ["a"],
    }


def test_extract_strips_think_then_extra_data():
    raw = '<think>reasoning</think>{"a": 1}{"b": 2}'
    assert _extract_json_from_text(raw) == {"a": 1}


def test_extract_returns_none_on_empty_or_garbage():
    assert _extract_json_from_text("") is None
    assert _extract_json_from_text("   \n  ") is None
    assert _extract_json_from_text("totally not json {{{") is None


class _ScriptedJsonRouter:
    """Yields a different text stream per call; lets us assert that the
    agent retries up to 3 times when each attempt returns garbage.
    """

    def __init__(self, streams: list[list[str]], model_id: str = "deepseek-v4-pro"):
        self._streams = streams
        self.calls = 0
        self._model_id = model_id

    def current_model_id(self) -> str:
        return self._model_id

    async def stream_json(self, messages, system=None, max_tokens=2048):
        index = min(self.calls, len(self._streams) - 1)
        self.calls += 1
        for chunk in self._streams[index]:
            yield {"type": "text_delta", "text": chunk}
        yield {"type": "usage", "input_tokens": 0, "output_tokens": 0}

    async def stream_with_tools(self, **kwargs):  # pragma: no cover - JSON path only
        if False:
            yield {}


def _state() -> GameState:
    return GameState(
        current_time="第1天·上午",
        current_location="x",
        player_inventory=[],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        time_index=0,
    )


def _world() -> dict:
    return {
        "base_setting": "test",
        "script_setting": "",
        "npc_descriptions": "",
        "ending_conditions": "",
    }


@pytest.mark.asyncio
async def test_agent_retries_then_succeeds_after_empty_output():
    router = _ScriptedJsonRouter(streams=[
        [""],
        ['{"quick_actions": ["go"]}'],
    ])
    agent = DirectorAgent(router, prefer_json_mode=True)
    result = await agent.run(
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        user_input="去看",
        game_mode="free",
    )
    assert router.calls == 2
    assert result.quick_actions == ["go"]


@pytest.mark.asyncio
async def test_agent_raises_parse_error_after_three_failures():
    router = _ScriptedJsonRouter(streams=[[""], [""], [""]])
    agent = DirectorAgent(router, prefer_json_mode=True)
    with pytest.raises(DirectorParseError):
        await agent.run(
            game_state=_state(),
            recent_messages=[],
            context_summary=None,
            world_data=_world(),
            user_input="去看",
            game_mode="free",
        )
    assert router.calls == 3
