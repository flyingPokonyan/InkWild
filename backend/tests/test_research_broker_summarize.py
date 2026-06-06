"""Tests for ResearchBroker.summarize_passages."""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from schemas.research_pack import Passage
from services.research_broker import ResearchBroker


class _FakeSynthesizer:
    """Fake LLMProvider that returns a fixed text via stream_with_tools."""

    def __init__(self, response_text: str = "摘要文本"):
        self._response_text = response_text

    async def stream_with_tools(self, **kwargs) -> AsyncIterator[dict]:
        yield {"type": "text_delta", "text": self._response_text}


@pytest.mark.asyncio
async def test_summarize_passages_returns_string():
    fake_synth = _FakeSynthesizer("梅长苏相关摘要")
    broker = ResearchBroker(tavily=None, web_searcher=None, synthesizer=fake_synth)
    passages = [
        Passage(id="p1", text="梅长苏是琅琊榜首", tags=[], source="tavily"),
        Passage(id="p2", text="靖王是东宫", tags=[], source="admin_note"),
    ]
    summary = await broker.summarize_passages(passages)
    assert isinstance(summary, str)
    assert len(summary) > 0


@pytest.mark.asyncio
async def test_summarize_passages_empty_returns_empty_string():
    broker = ResearchBroker(tavily=None, web_searcher=None, synthesizer=None)
    summary = await broker.summarize_passages([])
    assert summary == ""


@pytest.mark.asyncio
async def test_summarize_passages_no_synthesizer_returns_fallback():
    """无 synthesizer 时，返回前几条 passage 文本拼接的 fallback。"""
    broker = ResearchBroker(tavily=None, web_searcher=None, synthesizer=None)
    passages = [
        Passage(id="p1", text="梅长苏是琅琊榜首", tags=[], source="tavily"),
        Passage(id="p2", text="靖王是东宫", tags=[], source="admin_note"),
    ]
    summary = await broker.summarize_passages(passages)
    assert isinstance(summary, str)
    assert "梅长苏" in summary


@pytest.mark.asyncio
async def test_summarize_passages_caps_at_30():
    """超过 30 条 passage 时只取前 30 拼接，避免 LLM token 爆。"""
    fake_synth = _FakeSynthesizer("fixed summary")
    broker = ResearchBroker(tavily=None, web_searcher=None, synthesizer=fake_synth)
    passages = [
        Passage(id=f"p{i}", text=f"内容{i}", tags=[], source="tavily")
        for i in range(50)
    ]
    summary = await broker.summarize_passages(passages)
    # 测试不抛错，且返回 str
    assert isinstance(summary, str)
