import asyncio
import time

import pytest

from llm.base import WebSearchResult
from schemas.generation_strategy import ResearchRequest
from services.research_broker import ResearchBroker


class FakeTavily:
    def __init__(self):
        self.calls: list[str] = []

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        self.calls.append(query)
        return [{"title": query, "url": f"https://example.com/{query}", "content": f"{query} content"}]


class FakeWebSearcher:
    def __init__(self):
        self.calls: list[str] = []

    async def web_search(self, query: str, max_tokens: int = 2048) -> WebSearchResult:
        self.calls.append(query)
        return WebSearchResult(text=f"{query} web summary", query=query)


class EmptyWebSearcher:
    async def web_search(self, query: str, max_tokens: int = 2048) -> WebSearchResult:
        return WebSearchResult(query=query)


class SlowTavily:
    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        await asyncio.sleep(0.05)
        return [{"title": query, "url": f"https://example.com/{query}", "content": f"{query} content"}]


@pytest.mark.asyncio
async def test_research_broker_empty_request_returns_empty_context():
    broker = ResearchBroker()

    context = await broker.research(ResearchRequest(stage="events", query_candidates=[]))

    assert context.stage == "events"
    assert context.summary == ""
    assert context.artifacts == []


@pytest.mark.asyncio
async def test_research_broker_dedupes_queries_and_reuses_cache():
    tavily = FakeTavily()
    web = FakeWebSearcher()
    broker = ResearchBroker(tavily=tavily, web_searcher=web)

    request = ResearchRequest(stage="world_base", query_candidates=["维多利亚伦敦", "维多利亚伦敦", "白教堂"])
    first = await broker.research(request)
    second = await broker.research(request)

    assert len(first.artifacts) >= 2
    assert len(second.artifacts) >= 2
    assert tavily.calls == ["维多利亚伦敦", "白教堂"]
    assert web.calls == ["维多利亚伦敦", "白教堂"]


@pytest.mark.asyncio
async def test_research_broker_respects_query_cap():
    tavily = FakeTavily()
    broker = ResearchBroker(tavily=tavily)

    await broker.research(
        ResearchRequest(
            stage="characters",
            query_candidates=["a", "b", "c", "d"],
            max_queries=2,
        )
    )

    assert tavily.calls == ["a", "b"]


@pytest.mark.asyncio
async def test_research_broker_skips_empty_web_results():
    broker = ResearchBroker(web_searcher=EmptyWebSearcher())

    context = await broker.research(
        ResearchRequest(
            stage="world_base",
            query_candidates=["维多利亚伦敦"],
        )
    )

    assert context.artifacts == []
    assert context.summary == ""


@pytest.mark.asyncio
async def test_research_broker_executes_unique_queries_concurrently():
    broker = ResearchBroker(tavily=SlowTavily())

    started = time.perf_counter()
    await broker.research(
        ResearchRequest(
            stage="events",
            query_candidates=["a", "b"],
        )
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.09
