"""BUGS #20 — global LLM concurrency cap regression test."""
from __future__ import annotations

import asyncio

import pytest

import llm.router as router_module
from llm.base import LLMProvider
from llm.router import LLMRouter


class _CountingProvider(LLMProvider):
    """Provider whose stream holds the semaphore for `delay` seconds."""

    model = "fake-model"

    def __init__(self, in_flight_tracker: dict, delay: float = 0.05):
        self._tracker = in_flight_tracker
        self._delay = delay

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048,
                                response_format=None, tool_choice=None):
        self._tracker["now"] += 1
        self._tracker["peak"] = max(self._tracker["peak"], self._tracker["now"])
        try:
            await asyncio.sleep(self._delay)
            yield {"type": "text_delta", "text": "x"}
        finally:
            self._tracker["now"] -= 1

    async def stream_json(self, messages, system=None, max_tokens=2048):
        async for ev in self.stream_with_tools(messages, tools=[], system=system, max_tokens=max_tokens):
            yield ev


@pytest.mark.asyncio
async def test_global_concurrency_caps_peak_inflight(monkeypatch):
    # Reset module-level semaphore so it picks up our patched cap.
    monkeypatch.setattr(router_module, "_global_concurrency_sem", None)
    from config import settings as _settings
    monkeypatch.setattr(_settings, "llm_global_concurrency", 3)

    tracker = {"now": 0, "peak": 0}
    provider = _CountingProvider(tracker, delay=0.03)
    routers = [
        LLMRouter(providers={"p": provider}, fallback_chain=["p"])
        for _ in range(8)
    ]

    async def _drive(r: LLMRouter) -> None:
        async for _ in r.stream_with_tools(messages=[], tools=[]):
            pass

    await asyncio.gather(*[_drive(r) for r in routers])
    assert tracker["peak"] <= 3, f"peak inflight={tracker['peak']} exceeded cap=3"
    assert tracker["now"] == 0
