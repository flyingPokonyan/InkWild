import json
import pytest
from unittest.mock import MagicMock

from schemas.research_pack import IPCanon
from services.world_critic_service import (
    light_critic_lore,
    light_critic_shared_events,
)


def _make_router(text: str):
    fake = MagicMock()
    async def stream(*, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": text}
    fake.stream_with_tools = stream
    return fake


@pytest.mark.asyncio
async def test_lore_critic_returns_warnings():
    router = _make_router(json.dumps({"warnings": ["技术等级与 ip_canon 矛盾"]}))
    warnings = await light_critic_lore({"dimensions": [{"key": "x"}]}, IPCanon(), router)
    assert warnings == ["技术等级与 ip_canon 矛盾"]


@pytest.mark.asyncio
async def test_lore_critic_empty_pack_no_call():
    """空 lore_pack 不调 LLM，直接返回 []"""
    fake = MagicMock()
    async def boom(*, messages, tools, system, max_tokens):
        raise AssertionError("不应调用")
        yield
    fake.stream_with_tools = boom
    warnings = await light_critic_lore({"dimensions": []}, IPCanon(), fake)
    assert warnings == []


@pytest.mark.asyncio
async def test_lore_critic_invalid_json_returns_empty():
    router = _make_router("not json")
    warnings = await light_critic_lore({"dimensions": [{"key": "x"}]}, IPCanon(), router)
    assert warnings == []


@pytest.mark.asyncio
async def test_lore_critic_llm_failure_returns_empty():
    fake = MagicMock()
    async def boom(*, messages, tools, system, max_tokens):
        raise RuntimeError("5xx")
        yield
    fake.stream_with_tools = boom
    warnings = await light_critic_lore({"dimensions": [{"key": "x"}]}, IPCanon(), fake)
    assert warnings == []


@pytest.mark.asyncio
async def test_shared_events_critic_returns_warnings():
    router = _make_router(json.dumps({"warnings": ["事件 e1 与 ip_canon 历史不符"]}))
    events = [{"id": "e1", "title": "T", "summary": "S"}]
    warnings = await light_critic_shared_events(events, IPCanon(), router)
    assert warnings == ["事件 e1 与 ip_canon 历史不符"]


@pytest.mark.asyncio
async def test_shared_events_critic_empty_no_call():
    fake = MagicMock()
    async def boom(*, messages, tools, system, max_tokens):
        raise AssertionError("不应调用")
        yield
    fake.stream_with_tools = boom
    warnings = await light_critic_shared_events([], IPCanon(), fake)
    assert warnings == []
