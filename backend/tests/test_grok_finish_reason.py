"""Grok's stream_with_tools must also surface finish_reason in its usage event
(provider-usage contract, see llm/base.py)."""
from types import SimpleNamespace

import pytest

from llm.grok import GrokProvider


class _Stream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        self._it = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _Completions:
    def __init__(self, chunks):
        self._chunks = chunks

    async def create(self, **kwargs):
        return _Stream(self._chunks)


@pytest.mark.asyncio
async def test_stream_with_tools_usage_carries_finish_reason():
    provider = GrokProvider(api_key="test-key", model="grok-test")
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(content="片段", tool_calls=None),
                finish_reason=None)],
            usage=None),
        SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(content=None, tool_calls=None),
                finish_reason="length")],
            usage=SimpleNamespace(prompt_tokens=8, completion_tokens=3)),
    ]
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions(chunks)))
    events = [e async for e in provider.stream_with_tools(
        messages=[{"role": "user", "content": "x"}], tools=None, system="s")]
    usage = [e for e in events if e["type"] == "usage"][0]
    assert usage["finish_reason"] == "length"
