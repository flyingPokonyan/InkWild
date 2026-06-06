import json
import pytest
from unittest.mock import MagicMock

from schemas.research_pack import IPCanon, Passage
from schemas.character_v2 import Character
from schemas.shared_events import SharedEvent
from services.shared_events_builder import build_shared_events


def _make_router(responses: list[str]):
    fake = MagicMock()
    idx = {"n": 0}
    async def stream(*, messages, tools, system, max_tokens):
        i = idx["n"]; idx["n"] += 1
        yield {"type": "text_delta", "text": responses[i] if i < len(responses) else "{}"}
    fake.stream_with_tools = stream
    fake._calls = idx
    return fake


def _char(name, faction=""):
    return Character(name=name, personality=f"p_{name}", faction=faction)


@pytest.mark.asyncio
async def test_extract_with_source_passage_ids():
    passages = [
        Passage(id="p1", text="梅长苏与靖王在赤焰旧案中共同失去家人", tags=[], source="tavily"),
        Passage(id="p2", text="霓凰郡主与梅长苏儿时定亲", tags=[], source="tavily"),
    ]
    chars = [_char("梅长苏"), _char("靖王"), _char("霓凰郡主")]

    router_resp = json.dumps({
        "events": [
            {"id": "e1", "title": "赤焰旧案", "summary": "梅长苏靖王共同失家",
             "involved_npcs": ["梅长苏", "靖王"],
             "source_passage_ids": ["p1"]},
            {"id": "e2", "title": "儿时定亲", "summary": "霓凰梅长苏",
             "involved_npcs": ["梅长苏", "霓凰郡主"],
             "source_passage_ids": ["p2"]},
        ]
    })
    router = _make_router([router_resp])

    events = await build_shared_events(
        description="x", ip_canon=IPCanon(), characters=chars,
        passages=passages, llm_router=router,
    )
    assert len(events) == 2
    assert events[0].source_passage_ids == ["p1"]
    assert all(p_id in {"p1", "p2"} for e in events for p_id in e.source_passage_ids)


@pytest.mark.asyncio
async def test_invalid_passage_ids_filtered():
    """LLM 编造 passage id（不在输入列表里）应被过滤。"""
    passages = [Passage(id="p1", text="x", tags=[], source="tavily")]
    chars = [_char("A"), _char("B")]

    router_resp = json.dumps({
        "events": [
            {"id": "e1", "title": "T", "summary": "S",
             "involved_npcs": ["A", "B"],
             "source_passage_ids": ["p1", "p_FAKE"]},
        ]
    })
    router = _make_router([router_resp])

    events = await build_shared_events(
        description="x", ip_canon=IPCanon(), characters=chars,
        passages=passages, llm_router=router,
    )
    assert events[0].source_passage_ids == ["p1"]


@pytest.mark.asyncio
async def test_invalid_involved_npcs_filtered():
    passages = [Passage(id="p1", text="x", tags=[], source="tavily")]
    chars = [_char("A"), _char("B")]

    router_resp = json.dumps({
        "events": [
            {"id": "e1", "title": "T", "summary": "S",
             "involved_npcs": ["A", "B", "幽灵NPC"],
             "source_passage_ids": ["p1"]},
        ]
    })
    router = _make_router([router_resp])
    events = await build_shared_events(
        description="x", ip_canon=IPCanon(), characters=chars,
        passages=passages, llm_router=router,
    )
    assert "幽灵NPC" not in events[0].involved_npcs
    assert set(events[0].involved_npcs) == {"A", "B"}


@pytest.mark.asyncio
async def test_k_min_supplemented_when_below_threshold():
    """第一步只抽到 2 条 < k_min=5 → 第二次 LLM 补到 5 条（补的 events source_passage_ids 为空）。"""
    passages = [Passage(id="p1", text="x", tags=[], source="tavily")]
    chars = [_char("A"), _char("B")]

    first_resp = json.dumps({
        "events": [
            {"id": "e1", "title": "T1", "summary": "S", "involved_npcs": ["A"], "source_passage_ids": ["p1"]},
            {"id": "e2", "title": "T2", "summary": "S", "involved_npcs": ["B"], "source_passage_ids": []},
        ]
    })
    supplement_resp = json.dumps({
        "events": [
            {"id": "e3", "title": "T3", "summary": "S", "involved_npcs": ["A","B"], "source_passage_ids": []},
            {"id": "e4", "title": "T4", "summary": "S", "involved_npcs": ["A"], "source_passage_ids": []},
            {"id": "e5", "title": "T5", "summary": "S", "involved_npcs": ["B"], "source_passage_ids": []},
        ]
    })
    router = _make_router([first_resp, supplement_resp])

    events = await build_shared_events(
        description="x", ip_canon=IPCanon(), characters=chars,
        passages=passages, llm_router=router, k_target=15, k_min=5,
    )
    assert len(events) >= 5


@pytest.mark.asyncio
async def test_dedup_by_title():
    passages = [Passage(id="p1", text="x", tags=[], source="tavily")]
    chars = [_char("A")]
    router_resp = json.dumps({
        "events": [
            {"id": "e1", "title": "Same", "summary": "v1", "involved_npcs": ["A"], "source_passage_ids": ["p1"]},
            {"id": "e2", "title": "Same", "summary": "v2", "involved_npcs": ["A"], "source_passage_ids": ["p1"]},
        ]
    })
    router = _make_router([router_resp])
    events = await build_shared_events(
        description="x", ip_canon=IPCanon(), characters=chars,
        passages=passages, llm_router=router,
    )
    assert len(events) == 1


@pytest.mark.asyncio
async def test_llm_failure_returns_empty():
    fake = MagicMock()
    async def boom(**kw):
        raise RuntimeError("LLM 5xx")
        yield
    fake.stream_with_tools = boom
    events = await build_shared_events(
        description="x", ip_canon=IPCanon(), characters=[_char("A")],
        passages=[], llm_router=fake,
    )
    assert events == []


@pytest.mark.asyncio
async def test_invalid_json_returns_empty():
    router = _make_router(["not json"])
    events = await build_shared_events(
        description="x", ip_canon=IPCanon(), characters=[_char("A")],
        passages=[], llm_router=router,
    )
    assert events == []
