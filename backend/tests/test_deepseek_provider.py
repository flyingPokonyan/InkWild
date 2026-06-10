import pytest
from types import SimpleNamespace

from llm.deepseek import DeepSeekProvider, _convert_tool_to_openai


pytestmark = pytest.mark.no_db


def test_deepseek_provider_uses_config(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, *, api_key, base_url):
            captured["api_key"] = api_key
            captured["base_url"] = base_url

    monkeypatch.setattr("llm.deepseek.AsyncOpenAI", FakeClient)
    monkeypatch.setattr(
        "llm.deepseek.settings",
        SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_base_url="https://api.deepseek.com",
            llm_default_model="deepseek-chat",
        ),
    )

    provider = DeepSeekProvider()

    assert provider.model == "deepseek-chat"
    assert captured == {
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
    }


def test_convert_tool_to_openai():
    anthropic_tool = {
        "name": "update_game_state",
        "description": "更新状态",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
            },
            "required": ["location"],
        },
    }

    openai_tool = _convert_tool_to_openai(anthropic_tool)

    assert openai_tool["type"] == "function"
    assert openai_tool["function"]["name"] == "update_game_state"
    assert openai_tool["function"]["parameters"]["properties"]["location"]["type"] == "string"


@pytest.mark.asyncio
async def test_deepseek_provider_streams_text_and_tool_calls(monkeypatch):
    captured = {}

    class FakeStream:
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

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(content="第一段。", tool_calls=None),
                            )
                        ],
                        usage=None,
                    ),
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content="第二段。",
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=0,
                                            id="call_1",
                                            function=SimpleNamespace(
                                                name="update_game_state",
                                                arguments='{"location":"',
                                            ),
                                        )
                                    ],
                                ),
                            )
                        ],
                        usage=None,
                    ),
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=0,
                                            id=None,
                                            function=SimpleNamespace(name=None, arguments='码头"}'),
                                        )
                                    ],
                                ),
                            )
                        ],
                        usage=None,
                    ),
                    SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7)),
                ]
            )

    class FakeClient:
        def __init__(self, *, api_key, base_url):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("llm.deepseek.AsyncOpenAI", FakeClient)
    monkeypatch.setattr(
        "llm.deepseek.settings",
        SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_base_url="https://api.deepseek.com",
            llm_default_model="deepseek-chat",
        ),
    )

    provider = DeepSeekProvider()
    events = [event async for event in provider.stream_with_tools(
        messages=[{"role": "user", "content": "继续"}],
        tools=[{
            "name": "update_game_state",
            "description": "更新状态",
            "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}},
        }],
        system="你是旁白。",
    )]

    assert captured["stream"] is True
    assert captured["tool_choice"] == "auto"
    assert captured["stream_options"] == {"include_usage": True}
    assert events == [
        {"type": "text_delta", "text": "第一段。"},
        {"type": "text_delta", "text": "第二段。"},
        {"type": "tool_use_start", "name": "update_game_state", "id": "call_1"},
        {"type": "input_json_delta", "partial_json": '{"location":"'},
        {"type": "input_json_delta", "partial_json": '码头"}'},
        {"type": "tool_use", "name": "update_game_state", "input": {"location": "码头"}},
        {"type": "usage", "input_tokens": 12, "output_tokens": 7},
    ]


@pytest.mark.asyncio
async def test_deepseek_provider_counts_reasoning_content(monkeypatch):
    class FakeStream:
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

    class FakeCompletions:
        async def create(self, **kwargs):
            return FakeStream(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content=None,
                                    reasoning_content="先想一下",
                                    tool_calls=None,
                                ),
                            )
                        ],
                        usage=None,
                    ),
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content="正文。",
                                    reasoning_content=None,
                                    tool_calls=None,
                                ),
                            )
                        ],
                        usage=None,
                    ),
                    SimpleNamespace(
                        choices=[],
                        usage=SimpleNamespace(prompt_tokens=4, completion_tokens=3),
                    ),
                ]
            )

    class FakeClient:
        def __init__(self, *, api_key, base_url):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("llm.deepseek.AsyncOpenAI", FakeClient)
    monkeypatch.setattr(
        "llm.deepseek.settings",
        SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_base_url="https://api.deepseek.com",
            llm_default_model="deepseek-chat",
        ),
    )

    provider = DeepSeekProvider()
    events = [event async for event in provider.stream_with_tools(
        messages=[{"role": "user", "content": "继续"}],
        tools=[],
        system="你是旁白。",
    )]

    assert "".join(e["text"] for e in events if e["type"] == "text_delta") == "正文。"
    usage = next(e for e in events if e["type"] == "usage")
    assert usage["reasoning_content_chunks"] == 1
    assert usage["reasoning_content_chars"] == len("先想一下")
