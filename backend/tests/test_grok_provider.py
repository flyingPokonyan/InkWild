from types import SimpleNamespace

import pytest

from llm.grok import GrokProvider


class FakeResponsesAPI:
    def __init__(self, response: object | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


@pytest.mark.asyncio
async def test_web_search_uses_responses_api_and_extracts_citations():
    provider = GrokProvider(api_key="test-key", model="grok-test")
    response_api = FakeResponsesAPI(
        response=SimpleNamespace(
            output_text="Alpha Beta",
            output=[
                SimpleNamespace(
                    content=[
                        SimpleNamespace(
                            type="output_text",
                            text="Alpha Beta",
                            annotations=[
                                SimpleNamespace(url="https://example.com/source", title="Example Source"),
                            ],
                        )
                    ]
                )
            ],
        )
    )
    provider.client = SimpleNamespace(responses=response_api)

    result = await provider.web_search("Victorian London mystery", max_tokens=123)

    assert result.text == "Alpha Beta"
    assert result.citations == [
        {
            "url": "https://example.com/source",
            "title": "Example Source",
        }
    ]

    request = response_api.calls[0]
    assert request["model"] == "grok-test"
    assert request["input"] == [{"role": "user", "content": "Victorian London mystery"}]
    assert request["tools"] == [{"type": "web_search"}]
    assert request["max_output_tokens"] == 123


@pytest.mark.asyncio
async def test_web_search_disables_after_deprecated_error():
    provider = GrokProvider(api_key="test-key", model="grok-test")
    response_api = FakeResponsesAPI(
        error=RuntimeError("Live search is deprecated. Please switch to the Agent Tools API"),
    )
    provider.client = SimpleNamespace(responses=response_api)

    first = await provider.web_search("first query")
    second = await provider.web_search("second query")

    assert first.text == ""
    assert second.text == ""
    assert provider._web_search_disabled_reason == "deprecated"
    assert len(response_api.calls) == 1
