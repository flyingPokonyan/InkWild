"""Phase 8 tests: Director capability-based dispatch + prompt-mutation retry."""
import pytest
from typing import AsyncIterator

from engine.director_agent import DirectorAgent, DirectorParseError
from engine.state_manager import GameState


def _state():
    return GameState(current_time="day_1", current_location="A")


def _good_tool_result() -> dict:
    return {
        "involved_npcs": [],
        "npc_instructions": {},
        "scene_direction": "A quiet morning.",
        "state_updates": {},
        "quick_actions": [],
        "memory_extracts": [],
    }


class _FakeRouter:
    """Captures every call so the test can assert which path was taken."""

    def __init__(self, model_id: str):
        self.model_id = model_id
        self.tool_calls: list[dict] = []
        self.json_calls: list[dict] = []
        # Each entry is a list of events to yield for the matching call.
        self.tool_responses: list[list[dict]] = []
        self.json_responses: list[list[dict]] = []

    def current_model_id(self) -> str:
        return self.model_id

    async def stream_with_tools(self, **kwargs) -> AsyncIterator[dict]:
        self.tool_calls.append(kwargs)
        idx = len(self.tool_calls) - 1
        events = self.tool_responses[idx] if idx < len(self.tool_responses) else []
        for ev in events:
            yield ev

    async def stream_json(self, **kwargs) -> AsyncIterator[dict]:
        self.json_calls.append(kwargs)
        idx = len(self.json_calls) - 1
        events = self.json_responses[idx] if idx < len(self.json_responses) else []
        for ev in events:
            yield ev


@pytest.mark.asyncio
async def test_reasoning_model_dispatches_to_json_mode():
    router = _FakeRouter("deepseek-v4-pro")
    import json as _json
    router.json_responses = [[
        {"type": "text_delta", "text": _json.dumps(_good_tool_result())},
        {"type": "usage", "input_tokens": 1, "output_tokens": 1},
    ]]
    agent = DirectorAgent(router)
    result = await agent.run(
        game_state=_state(), recent_messages=[], context_summary=None,
        world_data={"base_setting": "x"}, user_input="hi", game_mode="script",
    )
    assert result.scene_direction == "A quiet morning."
    assert len(router.json_calls) == 1
    assert router.tool_calls == []


@pytest.mark.asyncio
async def test_claude_model_dispatches_to_forced_tool():
    router = _FakeRouter("claude-sonnet-4-6")
    router.tool_responses = [[
        {"type": "tool_use", "name": "director_decision", "input": _good_tool_result()},
        {"type": "usage", "input_tokens": 1, "output_tokens": 1},
    ]]
    agent = DirectorAgent(router)
    await agent.run(
        game_state=_state(), recent_messages=[], context_summary=None,
        world_data={"base_setting": "x"}, user_input="hi", game_mode="script",
    )
    assert len(router.tool_calls) == 1
    # tool_choice must be forced to director_decide
    assert router.tool_calls[0]["tool_choice"] == {
        "type": "function",
        "function": {"name": "director_decision"},
    }


@pytest.mark.asyncio
async def test_unknown_model_dispatches_to_tool_use_auto():
    router = _FakeRouter("brand-new-llm-v0")
    router.tool_responses = [[
        {"type": "tool_use", "name": "director_decision", "input": _good_tool_result()},
        {"type": "usage", "input_tokens": 1, "output_tokens": 1},
    ]]
    agent = DirectorAgent(router)
    await agent.run(
        game_state=_state(), recent_messages=[], context_summary=None,
        world_data={"base_setting": "x"}, user_input="hi", game_mode="script",
    )
    assert len(router.tool_calls) == 1
    # tool_choice is not forwarded (defaults to auto at provider layer)
    assert "tool_choice" not in router.tool_calls[0]


@pytest.mark.asyncio
async def test_prompt_mutation_on_retry_appends_feedback():
    router = _FakeRouter("deepseek-v4-pro")
    import json as _json
    router.json_responses = [
        [{"type": "text_delta", "text": "no json at all, just rambling"},
         {"type": "usage", "input_tokens": 1, "output_tokens": 1}],
        [{"type": "text_delta", "text": _json.dumps(_good_tool_result())},
         {"type": "usage", "input_tokens": 1, "output_tokens": 1}],
    ]
    agent = DirectorAgent(router)
    result = await agent.run(
        game_state=_state(), recent_messages=[], context_summary=None,
        world_data={"base_setting": "x"}, user_input="hi", game_mode="script",
    )
    assert result.scene_direction == "A quiet morning."
    assert len(router.json_calls) == 2
    # Second call's system must include the failure feedback.
    second_system = router.json_calls[1]["system"]
    assert "上一次输出的问题" in second_system or "无法解析" in second_system


@pytest.mark.asyncio
async def test_three_failures_raises_parse_error():
    router = _FakeRouter("deepseek-v4-pro")
    bad = [
        {"type": "text_delta", "text": "garbage"},
        {"type": "usage", "input_tokens": 1, "output_tokens": 1},
    ]
    router.json_responses = [bad, bad, bad]
    agent = DirectorAgent(router)
    with pytest.raises(DirectorParseError):
        await agent.run(
            game_state=_state(), recent_messages=[], context_summary=None,
            world_data={"base_setting": "x"}, user_input="hi", game_mode="script",
        )
    assert len(router.json_calls) == 3


@pytest.mark.asyncio
async def test_thinking_tag_stripped_before_json_parse():
    router = _FakeRouter("deepseek-v4-pro")
    import json as _json
    body = _json.dumps(_good_tool_result())
    router.json_responses = [[
        {"type": "text_delta",
         "text": f"<think>let me reason about this</think>{body}"},
        {"type": "usage", "input_tokens": 1, "output_tokens": 1},
    ]]
    agent = DirectorAgent(router)
    result = await agent.run(
        game_state=_state(), recent_messages=[], context_summary=None,
        world_data={"base_setting": "x"}, user_input="hi", game_mode="script",
    )
    assert result.scene_direction == "A quiet morning."


@pytest.mark.asyncio
async def test_recall_fn_does_not_downgrade_reasoning_model_off_json_mode():
    """Reasoning models stay on JSON mode even when recall_fn is supplied.

    Pre-2026-05-23 the agent downgraded to tool_use when recall was wired,
    on the theory that recall_memory needs tool plumbing. In practice the
    downgrade hurt Director stability far more than recall helped — the
    soak showed reasoning models drifting into empty-output failures under
    tool mode. recent_messages + memory_context cover most recall needs;
    losing the explicit recall tool on those models is acceptable.
    """
    import json as _json
    router = _FakeRouter("deepseek-v4-pro")
    router.json_responses = [[
        {"type": "text_delta", "text": _json.dumps(_good_tool_result())},
        {"type": "usage", "input_tokens": 1, "output_tokens": 1},
    ]]
    agent = DirectorAgent(router)
    await agent.run(
        game_state=_state(), recent_messages=[], context_summary=None,
        world_data={"base_setting": "x"}, user_input="hi", game_mode="script",
        recall_fn=lambda _k, _n: [],
    )
    assert len(router.json_calls) == 1
    assert router.tool_calls == []
