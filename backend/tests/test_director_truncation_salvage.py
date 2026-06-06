"""P0: director's climax JSON gets clipped mid-stream by the gateway → the
whole turn used to abort (HTTP 200, no narration) and the earned `ending_triggered`
was lost. Terminal-state partial-parse salvage recovers the front of the JSON so
scene_brief/ending_triggered survive a truncation."""
import pytest

from engine.director_agent import DirectorAgent


class _OneShotRouter:
    def __init__(self, text: str, finish_reason: str = "length"):
        self._text = text
        self._finish_reason = finish_reason
        self.calls = 0

    def current_model_id(self):
        return "deepseek-v4-pro"

    async def stream_json(self, messages, system=None, max_tokens=2048, provider_offset=0):
        self.calls += 1
        yield {"type": "text_delta", "text": self._text}
        yield {"type": "usage", "input_tokens": 0, "output_tokens": 0,
               "finish_reason": self._finish_reason}

    async def stream_with_tools(self, **kwargs):  # pragma: no cover - JSON path only
        if False:
            yield {}


@pytest.mark.asyncio
async def test_truncated_json_salvages_scene_brief_and_ending():
    # JSON cut off inside case_board_ops — not loadable as a whole.
    truncated = (
        '{"scene_brief": "皇后摊牌，甄嬛递上滴血的证物。",'
        ' "active_npcs": ["皇后"], "ending_triggered": {"should_end": true,'
        ' "ending_type": "good", "reason": "真相大白"}, "case_board_ops": ['
    )
    router = _OneShotRouter(truncated)
    agent = DirectorAgent(router)
    result = await agent._run_json_mode_raw(
        system="s", messages=[{"role": "user", "content": "摊牌"}],
        schema={"type": "object", "properties": {}},
    )
    assert result is not None
    usage_data, tool_input = result
    assert tool_input["scene_brief"].startswith("皇后摊牌")
    assert tool_input["ending_triggered"]["should_end"] is True
    assert router.calls == 1  # salvaged in place, no retry needed


@pytest.mark.asyncio
async def test_empty_shell_is_not_salvaged():
    # Partial parse yields a dict but with no load-bearing field → reject, so we
    # don't pass an empty shell off as success (caller will retry/abort instead).
    truncated = '{"active_npcs": ["皇后"], "dramatic_intensity": "hi'
    router = _OneShotRouter(truncated)
    agent = DirectorAgent(router)
    result = await agent._run_json_mode_raw(
        system="s", messages=[{"role": "user", "content": "x"}],
        schema={"type": "object", "properties": {}},
    )
    assert result is None
