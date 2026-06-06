"""Director truncation detection depends on the usage event carrying
``finish_reason``. openai_compatible is the provider the OpenCode gateway eval
ran on — it was silently dropping finish_reason, blinding the engine to its own
truncation. Pin that it now surfaces "length"."""
from types import SimpleNamespace

import pytest

from llm.openai_compatible import OpenAICompatibleProvider


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeCompletions:
    def __init__(self, chunks):
        self._chunks = chunks

    async def create(self, **kwargs):
        return _FakeStream(self._chunks)


def _make_provider(chunks):
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.model = "test-model"
    provider._reasoning_off_extra_body = None
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions(chunks))
    )
    return provider


@pytest.mark.asyncio
async def test_usage_event_carries_finish_reason_length():
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(content="部分文本", tool_calls=None),
                finish_reason=None)],
            usage=None),
        SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(content=None, tool_calls=None),
                finish_reason="length")],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5)),
    ]
    provider = _make_provider(chunks)
    events = [e async for e in provider.stream_with_tools(
        messages=[{"role": "user", "content": "x"}], tools=None, system="s")]
    usage = [e for e in events if e["type"] == "usage"][0]
    assert usage["finish_reason"] == "length"


@pytest.mark.asyncio
async def test_usage_event_finish_reason_stop_on_normal_completion():
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(content="完整", tool_calls=None),
                finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1)),
    ]
    provider = _make_provider(chunks)
    events = [e async for e in provider.stream_with_tools(
        messages=[{"role": "user", "content": "x"}], tools=None, system="s")]
    usage = [e for e in events if e["type"] == "usage"][0]
    assert usage["finish_reason"] == "stop"
