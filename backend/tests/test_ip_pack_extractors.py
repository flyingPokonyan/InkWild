"""Tests for IP pack extractors (wikipedia + tavily-site)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.ip_pack_extractors.wikipedia import fetch_wikipedia
from services.ip_pack_extractors.tavily_site import fetch_via_tavily_site


@pytest.mark.asyncio
async def test_wikipedia_404_returns_empty():
    fake_resp = MagicMock()
    fake_resp.status_code = 404
    fake_resp.raise_for_status = MagicMock()
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch("httpx.AsyncClient", return_value=fake_client):
        result = await fetch_wikipedia("不存在的IP")
        assert result == []


@pytest.mark.asyncio
async def test_wikipedia_parses_html():
    fake_html = "<html><body><div id='mw-content-text'>这是测试文本，超过若干字符。</div></body></html>"
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()
    fake_resp.text = fake_html
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch("httpx.AsyncClient", return_value=fake_client):
        result = await fetch_wikipedia("测试IP", max_chars=50)
        assert len(result) >= 1
        assert "测试文本" in result[0].text
        assert result[0].source == "wikipedia"


@pytest.mark.asyncio
async def test_tavily_site_aggregates_multi_sites():
    tavily = AsyncMock()
    tavily.search.side_effect = [
        [{"content": "百度内容", "url": "baike.baidu.com/x"}],
        [{"content": "豆瓣内容", "url": "douban.com/y"}],
    ]
    result = await fetch_via_tavily_site("逐玉", "tv", tavily, max_per_site=1)
    assert len(result) == 2
    assert any(any("baidu" in t for t in p.tags) for p in result)
    assert any(any("douban" in t for t in p.tags) for p in result)


@pytest.mark.asyncio
async def test_tavily_site_passes_include_domains():
    tavily = AsyncMock()
    tavily.search.return_value = []
    await fetch_via_tavily_site("逐玉", "tv", tavily, max_per_site=2)
    # tv → ["baike.baidu.com", "douban.com"]
    calls = tavily.search.call_args_list
    assert len(calls) == 2
    domains = [c.kwargs["include_domains"] for c in calls]
    assert ["baike.baidu.com"] in domains
    assert ["douban.com"] in domains
    # query should be just the ip_name, no `site:` prefix
    queries = [c.kwargs["query"] for c in calls]
    assert all(q == "逐玉" for q in queries)


@pytest.mark.asyncio
async def test_tavily_site_handles_partial_failure():
    tavily = AsyncMock()
    tavily.search.side_effect = [Exception("network"), [{"content": "ok", "url": "x"}]]
    result = await fetch_via_tavily_site("X", "tv", tavily)
    # 一个失败、一个成功 → 至少 1 条
    assert len(result) >= 1


@pytest.mark.asyncio
async def test_tavily_site_empty_when_no_ip_name():
    result = await fetch_via_tavily_site("", "tv", AsyncMock())
    assert result == []
