"""Pin the Narrator main-stream length cap. Pre-2026-05-24 this was
unbounded (router default 2048) and the soak produced 1064-2335 char
outputs per turn.

The prelude path was removed in the 2026-05 narrator simplification, so the
old prelude cap assertion is gone with it.
"""
from __future__ import annotations

import pytest

from engine.narrator_agent import NarratorAgent, _MAIN_MAX_TOKENS


class _CapturingRouter:
    def __init__(self):
        self.calls: list[dict] = []

    def current_model_id(self) -> str:
        return "test-model"

    async def stream_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        yield {"type": "text_delta", "text": "ok"}


@pytest.mark.asyncio
async def test_narrator_main_stream_passes_max_tokens():
    router = _CapturingRouter()
    agent = NarratorAgent(router)
    async for _ in agent.stream(
        scene_direction="紧张对峙",
        npc_dialogues={"老板": "你来这做什么"},
        recent_messages=[],
    ):
        pass
    assert router.calls[0]["max_tokens"] == _MAIN_MAX_TOKENS == 800
