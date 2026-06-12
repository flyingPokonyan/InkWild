"""Long-context robustness for the v2 director path (2026-06-11 100-round soak).

Two fixes pinned here:

1. **Empty-stream circuit breaker** — DeepSeek json_object mode degrades under
   long context by emitting hundreds of whitespace chars then ``finish_reason
   =stop``. The old loop drained the whole stream (30-60s) before declaring
   ``empty``. The breaker aborts as soon as the buffer crosses a threshold while
   still being all-whitespace, so a failed attempt costs ~seconds.

2. **Retry mode escalation** — empty/garbage output is *json_object*-specific.
   Retrying in the same mode re-hits the same degradation; escalating to forced
   tool_use samples a different mechanism (verified reliable on OpenCode
   deepseek-v4-pro with reasoning off).
"""
from __future__ import annotations

import pytest

from engine.director_agent import (
    DirectorAgent,
    _should_abort_empty_stream,
)
from engine.state_manager import GameState


# ---------------------------------------------------------------------------
# Fix 1 — pure helper
# ---------------------------------------------------------------------------


def test_abort_helper_false_below_threshold():
    # A few leading spaces are normal; don't abort prematurely.
    assert _should_abort_empty_stream("   ", threshold=64) is False


def test_abort_helper_false_when_real_content_present():
    # Once any non-whitespace shows up, it's a live stream — never abort.
    long_with_json = " " * 200 + '{"scene_brief"'
    assert _should_abort_empty_stream(long_with_json, threshold=64) is False


def test_abort_helper_true_on_whitespace_flood():
    # Hundreds of whitespace chars and nothing else = the degradation signature.
    assert _should_abort_empty_stream(" " * 120, threshold=64) is True


# ---------------------------------------------------------------------------
# v2 fixtures
# ---------------------------------------------------------------------------


class _ScriptedV2Router:
    """Replays a scripted json stream and/or a tool_use result per attempt,
    recording which structured-output mechanism each attempt invoked and how
    many json deltas were actually consumed (to detect early abort)."""

    def __init__(
        self,
        json_streams: list[list[str]] | None = None,
        tool_results: list[dict] | None = None,
        model_id: str = "deepseek-v4-pro",
    ):
        self._json_streams = json_streams or []
        self._tool_results = tool_results or []
        self._model_id = model_id
        self.json_calls = 0
        self.tool_calls = 0
        self.call_order: list[str] = []
        self.json_chunks_yielded = 0

    def current_model_id(self) -> str:
        return self._model_id

    async def stream_json(self, messages, system=None, max_tokens=2048, provider_offset=0):
        idx = min(self.json_calls, len(self._json_streams) - 1)
        self.json_calls += 1
        self.call_order.append("json")
        for chunk in self._json_streams[idx]:
            self.json_chunks_yielded += 1
            yield {"type": "text_delta", "text": chunk}
        yield {"type": "usage", "input_tokens": 0, "output_tokens": 0}

    async def stream_with_tools(self, **kwargs):
        idx = min(self.tool_calls, len(self._tool_results) - 1)
        self.tool_calls += 1
        self.call_order.append("tools")
        result = self._tool_results[idx] if self._tool_results else {}
        tool_name = kwargs["tools"][0]["name"]
        yield {"type": "tool_use", "name": tool_name, "input": result}
        yield {"type": "usage", "input_tokens": 0, "output_tokens": 0}


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


async def _run(agent: DirectorAgent):
    return await agent.run_v2(
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data=_world(),
        user_input="去看",
        game_mode="free",
    )


# ---------------------------------------------------------------------------
# Fix 1 — integration: whitespace flood is aborted early
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whitespace_flood_aborts_before_draining_stream():
    flood = [" " * 20] * 50  # 1000 whitespace chars, the dead signature
    good = ['{"quick_actions": ["go"]}']
    router = _ScriptedV2Router(
        json_streams=[flood, good],
        tool_results=[{"quick_actions": ["go"]}],
    )
    agent = DirectorAgent(router, prefer_json_mode=True)

    result = await _run(agent)

    # Breaker must stop well before draining all 50 whitespace chunks.
    assert router.json_chunks_yielded < 50
    # And the turn still recovers on retry (json or escalated tool).
    assert result.quick_actions == ["go"]


# ---------------------------------------------------------------------------
# Fix 2 — integration: empty json output escalates retry to forced tool_use
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_json_escalates_retry_to_tool_use():
    router = _ScriptedV2Router(
        json_streams=[[""]],  # attempt 0: empty json output
        tool_results=[{"quick_actions": ["recovered"]}],  # attempt 1: tool path
    )
    agent = DirectorAgent(router, prefer_json_mode=True)

    result = await _run(agent)

    assert router.call_order == ["json", "tools"]
    assert result.quick_actions == ["recovered"]
