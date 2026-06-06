"""Tests for build_research_pack — three-route merge."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from schemas.research_pack import IPCanon, Passage
from services.research_pack_builder import build_research_pack


@pytest.mark.asyncio
async def test_three_route_merge_priorities_admin_then_tavily():
    fake_broker = MagicMock()
    fake_broker.collect_passages = AsyncMock(return_value=[
        Passage(id="p_tav_1", text="t1", tags=[], source="tavily"),
        Passage(id="p_tav_2", text="t2", tags=[], source="tavily"),
    ])
    fake_broker.summarize_passages = AsyncMock(return_value="摘要")

    fake_router = MagicMock()

    async def fake_stream(*, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": '{"canonical_names":["梅长苏"]}'}

    fake_router.stream_with_tools = fake_stream

    pack = await build_research_pack(
        description="一段描述。\n\n第二段。",
        broker=fake_broker,
        llm_router=fake_router,
        max_passages=100,
        max_passage_chars=600,
    )

    sources = {p.source for p in pack.passages}
    assert sources == {"tavily", "admin_note"}  # ip_probe 不出 passage，只出 ip_canon
    assert "梅长苏" in pack.ip_canon.canonical_names
    assert pack.summary == "摘要"


@pytest.mark.asyncio
async def test_passages_capped_admin_priority():
    """max_passages 限制下，admin_note 优先全保留，剩余配额给 tavily。"""
    fake_broker = MagicMock()
    # 60 条 tavily passages
    fake_broker.collect_passages = AsyncMock(return_value=[
        Passage(id=f"p_tav_{i}", text=f"t{i}", tags=[], source="tavily")
        for i in range(60)
    ])
    fake_broker.summarize_passages = AsyncMock(return_value="")

    fake_router = MagicMock()

    async def fake_stream(*, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": "{}"}

    fake_router.stream_with_tools = fake_stream

    # 50 段 admin_note
    long_admin = "\n\n".join([f"段落{i}" for i in range(50)])
    pack = await build_research_pack(
        description=long_admin,
        broker=fake_broker, llm_router=fake_router,
        max_passages=80, max_passage_chars=600,
    )

    # 80 = 50 admin（全保留）+ 30 tavily（截断）
    assert len(pack.passages) == 80
    admin_count = sum(1 for p in pack.passages if p.source == "admin_note")
    tavily_count = sum(1 for p in pack.passages if p.source == "tavily")
    assert admin_count == 50
    assert tavily_count == 30


@pytest.mark.asyncio
async def test_three_routes_run_concurrently():
    """三路 IO 应该用 asyncio.gather 并发，不是串行。"""
    call_order: list[str] = []

    fake_broker = MagicMock()

    async def slow_collect(req, max_chars):
        call_order.append("tavily_start")
        await asyncio.sleep(0.05)
        call_order.append("tavily_done")
        return []

    fake_broker.collect_passages = slow_collect
    fake_broker.summarize_passages = AsyncMock(return_value="")

    fake_router = MagicMock()

    async def slow_stream(*, messages, tools, system, max_tokens):
        call_order.append("ip_probe_start")
        await asyncio.sleep(0.05)
        call_order.append("ip_probe_done")
        yield {"type": "text_delta", "text": "{}"}

    fake_router.stream_with_tools = slow_stream

    await build_research_pack(
        description="x", broker=fake_broker, llm_router=fake_router,
        max_passages=100, max_passage_chars=600,
    )

    # tavily_start 和 ip_probe_start 应在 tavily_done 和 ip_probe_done 之前都发生
    # （即并发，不是串行 tavily 全跑完再 ip_probe）
    tavily_start_idx = call_order.index("tavily_start")
    ip_probe_start_idx = call_order.index("ip_probe_start")
    tavily_done_idx = call_order.index("tavily_done")
    assert ip_probe_start_idx < tavily_done_idx, f"应并发，实际顺序：{call_order}"


@pytest.mark.asyncio
async def test_empty_description_no_passages():
    fake_broker = MagicMock()
    fake_broker.collect_passages = AsyncMock(return_value=[])
    fake_broker.summarize_passages = AsyncMock(return_value="")

    fake_router = MagicMock()

    async def fake_stream(*, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": "{}"}

    fake_router.stream_with_tools = fake_stream

    pack = await build_research_pack(
        description="",
        broker=fake_broker, llm_router=fake_router,
        max_passages=100, max_passage_chars=600,
    )
    assert pack.passages == []
    assert pack.summary == ""
