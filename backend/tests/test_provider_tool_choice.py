"""Phase 7 tests: provider tool_choice param + stream_json method."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from llm.deepseek import DeepSeekProvider


class _FakeAsyncStream:
    """Iterable that exposes chunks but supports `await client.create(...)`."""
    def __init__(self, chunks):
        self._chunks = chunks
    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()


@pytest.mark.asyncio
async def test_stream_with_tools_forwards_forced_tool_choice():
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeAsyncStream([])

    provider = DeepSeekProvider(model="deepseek-v4-pro")
    provider.client = MagicMock()
    provider.client.chat.completions.create = AsyncMock(side_effect=fake_create)

    async for _ in provider.stream_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "foo", "input_schema": {"type": "object"}}],
        tool_choice={"type": "function", "function": {"name": "foo"}},
    ):
        pass

    assert captured["tool_choice"] == {
        "type": "function",
        "function": {"name": "foo"},
    }


@pytest.mark.asyncio
async def test_stream_with_tools_default_is_auto():
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeAsyncStream([])

    provider = DeepSeekProvider(model="deepseek-v4-pro")
    provider.client = MagicMock()
    provider.client.chat.completions.create = AsyncMock(side_effect=fake_create)

    async for _ in provider.stream_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "foo", "input_schema": {"type": "object"}}],
    ):
        pass

    assert captured["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_stream_json_sets_response_format_and_yields_text():
    """stream_json uses response_format=json_object and yields text_delta + usage."""
    captured: dict = {}

    class FakeUsage:
        prompt_tokens = 10
        completion_tokens = 5

    def _chunk(content=None, usage=None):
        delta = MagicMock()
        delta.content = content
        choice = MagicMock()
        choice.delta = delta
        c = MagicMock()
        c.choices = [choice]
        c.usage = usage
        return c

    chunks = [
        _chunk(content="{"),
        _chunk(content='"a":1'),
        _chunk(content="}"),
        _chunk(usage=FakeUsage()),
    ]

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeAsyncStream(chunks)

    provider = DeepSeekProvider(model="deepseek-v4-pro")
    provider.client = MagicMock()
    provider.client.chat.completions.create = AsyncMock(side_effect=fake_create)

    events = []
    async for ev in provider.stream_json(
        messages=[{"role": "user", "content": "produce json"}],
        system="be terse",
    ):
        events.append(ev)

    # response_format forced to json_object
    assert captured["response_format"] == {"type": "json_object"}
    # No tools used
    assert "tools" not in captured

    text_events = [e for e in events if e["type"] == "text_delta"]
    usage_events = [e for e in events if e["type"] == "usage"]
    assert "".join(e["text"] for e in text_events) == '{"a":1}'
    assert len(usage_events) == 1
    assert usage_events[0]["input_tokens"] == 10
    assert usage_events[0]["output_tokens"] == 5
