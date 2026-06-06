import pytest
from unittest.mock import AsyncMock

from schemas.generation_strategy import ResearchRequest
from schemas.research_pack import Passage
from services.research_broker import ResearchBroker


@pytest.mark.asyncio
async def test_collect_passages_from_tavily():
    fake_tavily = AsyncMock()
    fake_tavily.search = AsyncMock(return_value=[
        {"title": "T1", "url": "https://example.com/1", "content": "原文段一" * 30},
        {"title": "T2", "url": "https://example.com/2", "content": "原文段二" * 50},
    ])
    broker = ResearchBroker(tavily=fake_tavily, web_searcher=None, synthesizer=None)
    req = ResearchRequest(stage="world_base", goal="g", query_candidates=["q1"])
    passages = await broker.collect_passages(req, max_chars=600)

    assert len(passages) == 2
    assert all(p.source == "tavily" for p in passages)
    assert all(len(p.text) <= 600 for p in passages)
    # 每个 passage 至少有 source URL tag
    assert any("source:" in tag for tag in passages[0].tags)


@pytest.mark.asyncio
async def test_collect_passages_empty_when_no_tavily():
    broker = ResearchBroker(tavily=None, web_searcher=None, synthesizer=None)
    req = ResearchRequest(stage="world_base", goal="g", query_candidates=["q1"])
    passages = await broker.collect_passages(req, max_chars=600)
    assert passages == []


@pytest.mark.asyncio
async def test_collect_passages_skips_empty_content():
    fake_tavily = AsyncMock()
    fake_tavily.search = AsyncMock(return_value=[
        {"title": "T1", "url": "u1", "content": ""},
        {"title": "T2", "url": "u2", "content": "有效内容"},
    ])
    broker = ResearchBroker(tavily=fake_tavily, web_searcher=None, synthesizer=None)
    req = ResearchRequest(stage="world_base", goal="g", query_candidates=["q1"])
    passages = await broker.collect_passages(req, max_chars=600)
    assert len(passages) == 1
    assert "有效内容" in passages[0].text


@pytest.mark.asyncio
async def test_collect_passages_handles_tavily_exception():
    fake_tavily = AsyncMock()
    fake_tavily.search = AsyncMock(side_effect=RuntimeError("Tavily 5xx"))
    broker = ResearchBroker(tavily=fake_tavily, web_searcher=None, synthesizer=None)
    req = ResearchRequest(stage="world_base", goal="g", query_candidates=["q1"])
    # 异常被吞，返回空 list（不抛）
    passages = await broker.collect_passages(req, max_chars=600)
    assert passages == []
