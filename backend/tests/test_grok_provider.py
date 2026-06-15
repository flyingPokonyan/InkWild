import json

import httpx
import pytest

from llm import grok as grok_module
from llm.grok import GrokProvider


def _sse_body(chunks: list[dict]) -> bytes:
    """Render OpenAI-style chat.completion.chunk objects as an SSE byte stream.

    Mirrors what the jiuuij gateway force-streams back even for non-stream
    requests — `data: {chunk}` lines terminated by `data: [DONE]`.
    """
    lines = [f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _patch_transport(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):  # noqa: ANN002, ANN003
        return real_client(transport=transport)

    monkeypatch.setattr(grok_module.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_web_search_parses_sse_and_extracts_citations(monkeypatch):
    """Gateway streams SSE; web_search must accumulate deltas + pull search_sources."""
    chunks = [
        {"choices": [{"delta": {"content": "Alpha "}}]},
        {
            "choices": [{"delta": {"content": "Beta"}}],
            "search_sources": [
                {"url": "https://example.com/source", "title": "Example Source"},
                {"url": "https://example.com/source", "title": "dup"},  # deduped by url
            ],
        },
    ]
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, content=_sse_body(chunks))

    _patch_transport(monkeypatch, handler)

    provider = GrokProvider(api_key="k", base_url="https://gw/v1", model="grok-test")
    result = await provider.web_search("Victorian London mystery", max_tokens=123)

    assert result.text == "Alpha Beta"
    assert result.citations == [
        {"url": "https://example.com/source", "title": "Example Source"}
    ]
    # request shape: chat.completions + Live Search params + explicit stream
    assert captured["url"].endswith("/chat/completions")
    assert captured["body"]["model"] == "grok-test"
    assert captured["body"]["stream"] is True
    assert captured["body"]["search_parameters"]["mode"] == "on"


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
async def test_web_search_malformed_chunks_are_skipped(monkeypatch):
    """A non-JSON data line shouldn't abort the whole parse."""
    body = (
        b"data: not-json\n\n"
        + _sse_body([{"choices": [{"delta": {"content": "ok"}}]}])
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    _patch_transport(monkeypatch, handler)

    provider = GrokProvider(api_key="k", base_url="https://gw/v1", model="grok-test")
    result = await provider.web_search("q")

    assert result.text == "ok"
