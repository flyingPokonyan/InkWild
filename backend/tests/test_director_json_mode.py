"""Phase 1.B.3 — DirectorAgent native JSON mode (with tool_use fallback)."""
from __future__ import annotations

import json

import pytest

from engine.director_agent import DirectorAgent
from engine.state_manager import GameState


class JsonRouter:
    """Captures kwargs (incl. response_format) and replays a scripted event stream.

    A new event list is consumed each call; if more calls than scripted lists
    happen, the last list is reused (so single-call tests stay simple).

    Both ``stream_with_tools`` and ``stream_json`` paths land in
    ``self.calls`` so existing assertions about response_format keep working
    even after the Director's capability-based dispatch refactor (Phase 8).
    """

    def __init__(self, event_lists: list[list[dict]], model_id: str = "test-model"):
        self.event_lists = event_lists
        self.calls: list[dict] = []
        self._model_id = model_id

    def current_model_id(self) -> str:
        return self._model_id

    async def stream_with_tools(
        self,
        messages,
        tools,
        system=None,
        response_format=None,
        tool_choice=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "system": system,
                "response_format": response_format,
                "tool_choice": tool_choice,
            }
        )
        index = min(len(self.calls) - 1, len(self.event_lists) - 1)
        for event in self.event_lists[index]:
            yield event

    async def stream_json(self, messages, system=None, max_tokens=2048):
        """Mirrors LLMProvider.stream_json default: routes through
        stream_with_tools with response_format=json_object and no tools.
        Lets old tests assert on ``router.calls[0]["response_format"]``.
        """
        async for ev in self.stream_with_tools(
            messages=messages,
            tools=[],
            system=system,
            response_format={"type": "json_object"},
        ):
            yield ev


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
        "base_setting": "雾隐镇是一个民国小镇。",
        "script_setting": "凶手是管家王福。",
        "npc_descriptions": "王福：忠厚寡言。",
        "ending_conditions": "当玩家指认凶手时触发完美结局。",
    }


def _valid_director_payload() -> dict:
    return {
        "involved_npcs": ["王福"],
        "npc_instructions": {"王福": "试探玩家。"},
        "scene_direction": "茶摊外起了风。",
        "state_updates": {"time_advance": True},
        "quick_actions": ["去茶摊", "询问王福"],
        "ending_triggered": {"should_end": False},
    }


async def _run_director(agent: DirectorAgent):
    return await agent.run(
        game_state=_make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_make_world_data(),
        user_input="我去茶摊",
        game_mode="script",
        memory_context="",
    )


@pytest.mark.asyncio
async def test_json_mode_off_uses_tool_use_path_unchanged():
    router = JsonRouter(
        [
            [
                {
                    "type": "tool_use",
                    "name": "director_decision",
                    "input": _valid_director_payload(),
                },
                {"type": "usage", "input_tokens": 1, "output_tokens": 1},
            ]
        ]
    )
    agent = DirectorAgent(router, prefer_json_mode=False)
    result = await _run_director(agent)

    assert result.involved_npcs == ["王福"]
    # No JSON mode → no response_format passed.
    assert router.calls[0]["response_format"] is None
    # Tool path always passes director_decision tool.
    assert router.calls[0]["tools"][0]["name"] == "director_decision"


@pytest.mark.asyncio
async def test_json_mode_on_uses_response_format_and_parses_text_stream():
    payload = _valid_director_payload()
    router = JsonRouter(
        [
            [
                {"type": "text_delta", "text": json.dumps(payload, ensure_ascii=False)},
                {"type": "usage", "input_tokens": 1, "output_tokens": 1},
            ]
        ]
    )
    agent = DirectorAgent(router, prefer_json_mode=True)
    result = await _run_director(agent)

    assert result.involved_npcs == ["王福"]
    assert result.scene_direction == "茶摊外起了风。"
    # JSON mode call carries response_format and no tools.
    first_call = router.calls[0]
    assert first_call["response_format"] == {"type": "json_object"}
    assert first_call["tools"] == []
    # JSON-mode system suffix is appended.
    assert "JSON Schema" in first_call["system"]


@pytest.mark.asyncio
async def test_json_mode_handles_code_fenced_output():
    payload = _valid_director_payload()
    fenced = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    router = JsonRouter(
        [
            [
                {"type": "text_delta", "text": fenced},
                {"type": "usage", "input_tokens": 1, "output_tokens": 1},
            ]
        ]
    )
    agent = DirectorAgent(router, prefer_json_mode=True)
    result = await _run_director(agent)
    assert result.involved_npcs == ["王福"]


@pytest.mark.asyncio
async def test_json_mode_retries_with_prompt_mutation_on_malformed_output():
    """Phase 8 behavior change: JSON-mode failure retries JSON mode itself
    with mutated prompt — NOT falls back to tool_use. The old fallback
    silently masked the root cause; prompt mutation surfaces it.
    """
    payload = _valid_director_payload()
    router = JsonRouter(
        [
            [{"type": "text_delta", "text": "this is not JSON"},
             {"type": "usage", "input_tokens": 1, "output_tokens": 1}],
            [{"type": "text_delta", "text": json.dumps(payload, ensure_ascii=False)},
             {"type": "usage", "input_tokens": 1, "output_tokens": 1}],
        ]
    )
    agent = DirectorAgent(router, prefer_json_mode=True)
    result = await _run_director(agent)

    assert result.involved_npcs == ["王福"]
    assert len(router.calls) == 2
    # Both calls stayed on JSON mode.
    assert router.calls[0]["response_format"] == {"type": "json_object"}
    assert router.calls[1]["response_format"] == {"type": "json_object"}
    # Second call's system carries the failure feedback.
    assert "上一次输出的问题" in router.calls[1]["system"] or "无法解析" in router.calls[1]["system"]


@pytest.mark.asyncio
async def test_json_mode_stays_on_when_recall_fn_provided():
    """JSON mode is materially more reliable for reasoning models such as
    DeepSeek V4 Pro; recall_fn presence no longer downgrades to tool_use.
    The model loses access to recall_memory but keeps stable structured
    output — net win per the 2026-05-23 soak (Director parse failures
    dominated; recall hits were rare).
    """
    payload = _valid_director_payload()
    router = JsonRouter([
        [
            {"type": "text_delta", "text": json.dumps(payload)},
            {"type": "usage", "input_tokens": 1, "output_tokens": 1},
        ]
    ])
    agent = DirectorAgent(router, prefer_json_mode=True)
    await agent.run(
        game_state=_make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_make_world_data(),
        user_input="我观察",
        game_mode="script",
        memory_context="",
        recall_fn=lambda keyword, max_results=3: [],
    )
    assert router.calls[0]["response_format"] == {"type": "json_object"}
    assert router.calls[0]["tools"] == []
