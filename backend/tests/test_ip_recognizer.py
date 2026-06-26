"""Tests for Stage 0 IP recognizer."""
import pytest
from unittest.mock import AsyncMock

from services.ip_recognizer import recognize_ip


class FakeLLM:
    """Minimal stub that yields the given text as a stream of text_delta events."""
    def __init__(self, text: str):
        self._text = text

    async def stream_with_tools(self, **_kwargs):
        for ch in self._text:
            yield {"type": "text_delta", "text": ch}


@pytest.mark.asyncio
async def test_recognize_known_ip():
    llm = FakeLLM('{"kind":"known_ip","confidence":0.9,"ip_name":"逐玉","ip_type":"tv","one_liner":"古装爱情剧","source_hints":["逐玉 百度百科"]}')
    rec = await recognize_ip("影视剧 逐玉", llm_router=llm)
    assert rec.kind == "known_ip"
    assert rec.ip_name == "逐玉"
    assert rec.ip_type == "tv"


@pytest.mark.asyncio
async def test_recognize_original_returns_original():
    llm = FakeLLM('{"kind":"original","confidence":0.95}')
    rec = await recognize_ip("未来火星上的官僚社会", llm_router=llm)
    assert rec.kind == "original"
    assert rec.ip_name is None


@pytest.mark.asyncio
async def test_recognize_empty_input():
    llm = FakeLLM("")
    rec = await recognize_ip("   ", llm_router=llm)
    assert rec.kind == "original"
    assert rec.confidence == 0.0


@pytest.mark.asyncio
async def test_recognize_llm_garbage_falls_back():
    llm = FakeLLM("not json at all")
    rec = await recognize_ip("X", llm_router=llm)
    assert rec.kind == "original"


@pytest.mark.asyncio
async def test_tavily_verify_promotes_confidence():
    llm = FakeLLM('{"kind":"known_ip","confidence":0.7,"ip_name":"逐玉","ip_type":"tv"}')
    tavily = AsyncMock()
    tavily.search.return_value = [{"title": "逐玉 - 维基百科", "url": "..."}]
    rec = await recognize_ip("逐玉", llm_router=llm, tavily=tavily)
    assert rec.confidence > 0.7  # promoted


@pytest.mark.asyncio
async def test_tavily_verify_demotes_confidence_when_no_match():
    llm = FakeLLM('{"kind":"known_ip","confidence":0.7,"ip_name":"逐玉","ip_type":"tv"}')
    tavily = AsyncMock()
    tavily.search.return_value = [{"title": "无关结果", "url": "..."}]
    rec = await recognize_ip("逐玉", llm_router=llm, tavily=tavily)
    assert rec.confidence < 0.7


@pytest.mark.asyncio
async def test_web_search_rescues_misjudged_original(monkeypatch):
    """裸标题网文（如「十日终焉」）：参数快判 original，联网取证后复判 known_ip。"""
    class TwoPassLLM:
        async def stream_with_tools(self, **kwargs):
            user = kwargs["messages"][0]["content"]
            if "联网检索资料" in user:  # Pass 2：带证据
                text = ('{"kind":"known_ip","confidence":0.9,"ip_name":"十日终焉",'
                        '"ip_type":"novel","one_liner":"齐夏的终焉游戏",'
                        '"source_hints":["十日终焉 杀虫队队员"]}')
            else:  # Pass 1：纯参数
                text = '{"kind":"original","confidence":0.85}'
            for ch in text:
                yield {"type": "text_delta", "text": ch}

    async def fake_evidence(_llm, _description):
        return "十日终焉：番茄小说无限流网文，作者杀虫队队员，主角齐夏。"

    monkeypatch.setattr("services.ip_recognizer._web_search_evidence", fake_evidence)
    rec = await recognize_ip("十日终焉", llm_router=TwoPassLLM())
    assert rec.kind == "known_ip"
    assert rec.ip_name == "十日终焉"
    assert rec.ip_type == "novel"


@pytest.mark.asyncio
async def test_no_rescue_when_search_yields_nothing(monkeypatch):
    """检索无证据（未配 grok / 真原创）时维持 original，不误判。"""
    async def empty_evidence(_llm, _description):
        return ""

    monkeypatch.setattr("services.ip_recognizer._web_search_evidence", empty_evidence)
    llm = FakeLLM('{"kind":"original","confidence":0.9}')
    rec = await recognize_ip("一个纯粹虚构的泛概念", llm_router=llm)
    assert rec.kind == "original"
    assert rec.ip_name is None


@pytest.mark.asyncio
async def test_tavily_verify_downgrades_to_hybrid_when_confidence_drops_low():
    # confidence 0.65 - 0.20 = 0.45 → below 0.5 → kind demoted to "hybrid"
    llm = FakeLLM('{"kind":"known_ip","confidence":0.65,"ip_name":"逐玉","ip_type":"tv"}')
    tavily = AsyncMock()
    tavily.search.return_value = [{"title": "完全无关的搜索结果", "url": "..."}]
    rec = await recognize_ip("逐玉", llm_router=llm, tavily=tavily)
    assert rec.kind == "hybrid"
    assert rec.confidence < 0.5
