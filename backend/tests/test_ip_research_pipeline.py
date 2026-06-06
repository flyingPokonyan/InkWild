"""Tests for IP research pipeline (mock LLM + mock extractors)."""
import pytest
from unittest.mock import AsyncMock, patch

from schemas.research_pack import Passage
from services.ip_recognizer import IPRecognition
from services.ip_research_pipeline import build_ip_knowledge_pack


class FakeLLM:
    """Sequential text streamer — each call yields the next predefined text."""
    def __init__(self, *texts: str):
        self._texts = list(texts)
        self._idx = 0

    async def stream_with_tools(self, **_kwargs):
        text = self._texts[min(self._idx, len(self._texts) - 1)]
        self._idx += 1
        for ch in text:
            yield {"type": "text_delta", "text": ch}


@pytest.mark.asyncio
async def test_pipeline_returns_empty_when_kind_is_original():
    rec = IPRecognition(kind="original", confidence=0.0)
    pack = await build_ip_knowledge_pack(rec, "strict", llm_router=FakeLLM(""), tavily=AsyncMock())
    assert pack.characters == []
    assert pack.places == []
    assert pack.ip_name == ""


@pytest.mark.asyncio
async def test_pipeline_returns_empty_when_no_ip_name():
    rec = IPRecognition(kind="known_ip", confidence=0.9, ip_name=None)
    pack = await build_ip_knowledge_pack(rec, "strict", llm_router=FakeLLM(""), tavily=AsyncMock())
    assert pack.characters == []


@pytest.mark.asyncio
async def test_pipeline_extracts_pack_from_passages():
    rec = IPRecognition(kind="known_ip", confidence=0.9, ip_name="逐玉", ip_type="tv")
    extract_json = '{"summary":"屠户女与落难侯爷的故事","characters":[{"name":"樊长玉","role_in_story":"女主","relation_to_protagonist":"本人","traits":[],"must_have":true,"source_passage_ids":["p1"]}],"places":[{"name":"临安镇","description":"","must_have":true,"source_passage_ids":["p1"]}],"factions":[],"iconic_objects":[],"key_events":[],"tone_lingo":[]}'
    missing_json = '{"missing_names":[]}'
    llm = FakeLLM(extract_json, missing_json)
    tavily = AsyncMock()
    tavily.search.return_value = [{"content": "樊长玉 谢征 临安镇", "url": "x", "title": "t"}]

    with patch("services.ip_research_pipeline.fetch_wikipedia",
               new=AsyncMock(return_value=[Passage(id="p1", text="...", tags=[], source="wikipedia")])):
        pack = await build_ip_knowledge_pack(rec, "strict", llm_router=llm, tavily=tavily)

    assert pack.ip_name == "逐玉"
    assert pack.fidelity_mode == "strict"
    assert "樊长玉" in pack.must_have_character_names()
    assert "临安镇" in pack.must_have_place_names()


@pytest.mark.asyncio
async def test_pipeline_self_check_triggers_extra_fetch():
    rec = IPRecognition(kind="known_ip", confidence=0.9, ip_name="逐玉", ip_type="tv")
    first_extract = '{"summary":"long enough summary","characters":[{"name":"樊长玉","role_in_story":"女主","relation_to_protagonist":"本人","traits":[],"must_have":true,"source_passage_ids":[]}],"places":[],"factions":[],"iconic_objects":[],"key_events":[],"tone_lingo":[]}'
    missing_json = '{"missing_names":["李怀安","谢征"]}'
    second_extract = '{"summary":"S2","characters":[{"name":"樊长玉","role_in_story":"女主","relation_to_protagonist":"本人","traits":[],"must_have":true,"source_passage_ids":[]},{"name":"李怀安","role_in_story":"配角","relation_to_protagonist":"师兄","traits":[],"must_have":true,"source_passage_ids":[]}],"places":[],"factions":[],"iconic_objects":[],"key_events":[],"tone_lingo":[]}'
    llm = FakeLLM(first_extract, missing_json, second_extract)
    tavily = AsyncMock()
    tavily.search.return_value = [{"content": "李怀安相关", "url": "x", "title": "t"}]

    with patch("services.ip_research_pipeline.fetch_wikipedia",
               new=AsyncMock(return_value=[Passage(id="p1", text="...", tags=[], source="wikipedia")])):
        pack = await build_ip_knowledge_pack(rec, "strict", llm_router=llm, tavily=tavily)
    char_names = [c.name for c in pack.characters]
    assert "李怀安" in char_names


@pytest.mark.asyncio
async def test_pipeline_no_passages_returns_skeleton():
    rec = IPRecognition(kind="known_ip", confidence=0.9, ip_name="冷门IP", ip_type="other")
    tavily = AsyncMock()
    tavily.search.return_value = []

    with patch("services.ip_research_pipeline.fetch_wikipedia",
               new=AsyncMock(return_value=[])), \
         patch("services.ip_research_pipeline.fetch_via_tavily_site",
               new=AsyncMock(return_value=[])):
        pack = await build_ip_knowledge_pack(rec, "loose", llm_router=FakeLLM(""), tavily=tavily)
    assert pack.ip_name == "冷门IP"
    assert pack.characters == []
    assert pack.summary == ""


@pytest.mark.asyncio
async def test_pipeline_missing_names_but_empty_supplementary_returns_first_pack():
    """When self-check says missing names but supplementary tavily returns nothing,
    the original pack (not a degraded re-extract) is returned."""
    rec = IPRecognition(kind="known_ip", confidence=0.9, ip_name="逐玉", ip_type="tv")
    first_extract = '{"summary":"S","characters":[{"name":"樊长玉","role_in_story":"女主","relation_to_protagonist":"本人","traits":[],"must_have":true,"source_passage_ids":[]}],"places":[],"factions":[],"iconic_objects":[],"key_events":[],"tone_lingo":[]}'
    missing_json = '{"missing_names":["李怀安","谢征"]}'
    # Note: no third LLM response — pipeline should NOT call extract a second time
    llm = FakeLLM(first_extract, missing_json)

    with patch("services.ip_research_pipeline.fetch_wikipedia",
               new=AsyncMock(return_value=[Passage(id="p1", text="...", tags=[], source="wikipedia")])), \
         patch("services.ip_research_pipeline.fetch_via_tavily_site",
               new=AsyncMock(return_value=[])):  # supplementary returns empty
        pack = await build_ip_knowledge_pack(rec, "strict", llm_router=llm, tavily=AsyncMock())
    char_names = [c.name for c in pack.characters]
    assert char_names == ["樊长玉"]  # only the original 1, no re-extract happened


@pytest.mark.asyncio
async def test_pre_extract_drops_malformed_timeline_entry_instead_of_raising():
    """Regression: 2026-05-19 大奉打更人 failure.

    LLM emitted a timeline entry with `description` instead of the required
    `event` field. The unguarded list comprehension raised ValidationError,
    aborted the whole pack construction, and the agent silently swallowed it —
    admin saw "ip_research completed" with ip_name=null and the world was
    generated with no canon anchors.

    The fix is `_safe_build_list`: a malformed entry is dropped with a warn,
    the rest of the pack survives.
    """
    from services.ip_research_pipeline import _pre_extract_canon

    rec = IPRecognition(kind="known_ip", confidence=1.0, ip_name="大奉打更人", ip_type="novel")
    # timeline[0] uses `description` (LLM drift) — used to kill the whole pack.
    # timeline[1] is well-formed — must survive.
    extract_json = (
        '{"summary":"打更人查案","characters":['
        '{"name":"许七安","role_in_story":"主角","relation_to_protagonist":"本人",'
        '"traits":[],"must_have":true,"source_passage_ids":[]}],'
        '"places":[],"factions":[],"iconic_objects":[],"key_events":[],'
        '"tone_lingo":[],'
        '"timeline":['
        '{"when":"中段","description":"卷入皇室内斗"},'
        '{"when":"结局","event":"许七安飞升"}'
        ']}'
    )
    pack = await _pre_extract_canon(rec, FakeLLM(extract_json))

    assert pack.ip_name == "大奉打更人"
    assert [c.name for c in pack.characters] == ["许七安"]
    # Bad timeline entry dropped, valid one preserved — no ValidationError raised.
    assert [t.event for t in pack.timeline] == ["许七安飞升"]
