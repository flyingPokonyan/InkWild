import asyncio
import json

import httpx
import pytest

from llm import grok as grok_module
from llm.grok import GrokProvider


def _patch_transport(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):  # noqa: ANN002, ANN003
        return real_client(transport=transport)

    monkeypatch.setattr(grok_module.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_web_search_uses_responses_api_and_extracts_citations(monkeypatch):
    response = {
        "citations": ["https://example.com/top-level"],
        "output": [
            {"type": "web_search_call", "status": "completed"},
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Alpha Beta",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://example.com/source",
                                "title": "Example Source",
                            },
                            {
                                "type": "url_citation",
                                "url": "https://example.com/source",
                                "title": "duplicate",
                            },
                        ],
                    }
                ],
            },
        ],
    }
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=response)

    _patch_transport(monkeypatch, handler)

    provider = GrokProvider(api_key="k", base_url="https://gw/v1", model="grok-test")
    result = await provider.web_search("Victorian London mystery", max_tokens=123)

    assert result.text == "Alpha Beta"
    assert result.citations == [
        {"url": "https://example.com/top-level", "title": ""},
        {"url": "https://example.com/source", "title": "Example Source"}
    ]
    assert captured["url"].endswith("/responses")
    assert captured["body"]["model"] == "grok-test"
    assert captured["body"]["max_output_tokens"] == 123
    assert captured["body"]["max_tool_calls"] == 8
    assert captured["body"]["tools"] == [{"type": "web_search"}]


@pytest.mark.asyncio
async def test_web_search_non_200_returns_empty(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"upstream boom")

    _patch_transport(monkeypatch, handler)

    provider = GrokProvider(api_key="k", base_url="https://gw/v1", model="grok-test")
    result = await provider.web_search("q")

    assert result.text == ""
    assert result.citations == []


@pytest.mark.asyncio
async def test_web_search_malformed_json_returns_empty(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    _patch_transport(monkeypatch, handler)

    provider = GrokProvider(api_key="k", base_url="https://gw/v1", model="grok-test")
    result = await provider.web_search("q")

    assert result.text == ""
    assert result.citations == []


@pytest.mark.asyncio
async def test_web_search_has_total_wall_clock_timeout(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            await asyncio.sleep(60)

    monkeypatch.setattr(grok_module.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(grok_module.settings, "grok_web_search_total_timeout_seconds", 0.02)
    provider = GrokProvider(api_key="k", base_url="https://gw/v1", model="grok-test")

    result = await provider.web_search("q")

    assert result.text == ""
