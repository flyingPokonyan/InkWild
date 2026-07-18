"""Tests for events_data_builder."""
import json
import pytest
from unittest.mock import MagicMock

from schemas.research_pack import IPCanon
from schemas.character_v2 import Character
from schemas.shared_events import SharedEvent
from schemas.lore_pack import LorePack
from services.events_data_builder import build_events_data


def _make_router(responses: list[str]):
    fake = MagicMock()
    idx = {"n": 0}
    prompts: list[str] = []

    async def stream(*, messages, tools, system, max_tokens):
        prompts.append(messages[0]["content"])
        i = idx["n"]
        idx["n"] += 1
        yield {"type": "text_delta", "text": responses[i] if i < len(responses) else "{}"}

    fake.stream_with_tools = stream
    fake._calls = idx
    fake._prompts = prompts
    return fake


def _ch(name): return Character(name=name, personality="p")


def _ev_json(eid, kind="conditional", npc_name=None, dsl="time_after('day_3')", **extra):
    if kind == "npc_intent_driven":
        trigger = {"npc_name": npc_name, "condition_dsl": dsl, "intent_payload": {}}
    else:
        trigger = {"condition_dsl": dsl, "probability": 0.7}
    return {
        "id": eid, "kind": kind, "summary": f"S{eid}",
        "trigger": trigger,
        "effects": {"world_state_changes": {}, "spawn_clues": [], "npc_mood_changes": {}},
        "rumors": [],
        **extra,
    }


@pytest.mark.asyncio
async def test_basic_generation_one_batch():
    chars = [_ch("A"), _ch("B")]
    resp = json.dumps({"events": [
        _ev_json("e1"),
        _ev_json("e2", kind="npc_intent_driven", npc_name="A"),
    ]})
    router = _make_router([resp])

    events = await build_events_data(
        description="x", ip_canon=IPCanon(), characters=chars,
        locations=["朝堂"], shared_events=[], lore_pack=LorePack(),
        llm_router=router, target_count=2, batch_size=5,
    )
    assert len(events) == 2
    assert all(not e.disabled for e in events)


@pytest.mark.asyncio
async def test_spawn_clues_dict_coerced_to_string():
    """LLM sometimes emits spawn_clues as ``[{clue_id, description, location}]``
    instead of the schema's ``list[str]``. The builder must coerce dicts to
    plain strings using the description field (or the dict's text payload)
    so downstream EventEffects validation doesn't fail.
    """
    chars = [_ch("A")]
    resp = json.dumps({"events": [{
        "id": "e1",
        "kind": "conditional",
        "summary": "S",
        "trigger": {"condition_dsl": "time_after('day_3')", "probability": 0.5},
        "effects": {
            "world_state_changes": {},
            "spawn_clues": [
                {"clue_id": "bloodstained_bandage", "description": "草庐中带血的绷带", "location": "草庐"},
                "plain string clue",
                {"description": "no clue_id, no location, only description"},
            ],
            "npc_mood_changes": {},
        },
        "rumors": [],
    }]})
    router = _make_router([resp])
    events = await build_events_data(
        description="x", ip_canon=IPCanon(), characters=chars,
        locations=[], shared_events=[], lore_pack=LorePack(),
        llm_router=router, target_count=1, batch_size=5,
    )
    assert len(events) == 1
    assert not events[0].disabled
    clues = events[0].effects.spawn_clues
    assert clues == [
        "草庐中带血的绷带",
        "plain string clue",
        "no clue_id, no location, only description",
    ]


@pytest.mark.asyncio
async def test_invalid_dsl_disables_event():
    chars = [_ch("A")]
    resp = json.dumps({"events": [
        _ev_json("e1", dsl="time_after('day_3')"),  # OK
        _ev_json("e2", dsl="bogus syntax !!!"),     # parse fail
    ]})
    router = _make_router([resp])
    events = await build_events_data(
        description="x", ip_canon=IPCanon(), characters=chars,
        locations=[], shared_events=[], lore_pack=LorePack(),
        llm_router=router, target_count=2, batch_size=5,
    )
    by_id = {e.id: e for e in events}
    assert by_id["e1"].disabled is False
    assert by_id["e2"].disabled is True
    assert "dsl" in by_id["e2"].disabled_reason.lower()


@pytest.mark.asyncio
async def test_invalid_npc_name_disables():
    chars = [_ch("A")]
    resp = json.dumps({"events": [
        _ev_json("e1", kind="npc_intent_driven", npc_name="幽灵NPC"),
    ]})
    router = _make_router([resp])
    events = await build_events_data(
        description="x", ip_canon=IPCanon(), characters=chars,
        locations=[], shared_events=[], lore_pack=LorePack(),
        llm_router=router, target_count=1, batch_size=5,
    )
    assert events[0].disabled is True


@pytest.mark.asyncio
async def test_invalid_rumor_knowers_filtered():
    chars = [_ch("A"), _ch("B")]
    resp = json.dumps({"events": [{
        "id": "e1", "kind": "conditional", "summary": "S",
        "trigger": {"condition_dsl": "time_after('day_3')", "probability": 1.0},
        "effects": {"world_state_changes": {}, "spawn_clues": [], "npc_mood_changes": {}},
        "rumors": [
            {"text": "rumor1", "knower_npcs": ["A", "幽灵"]},
            {"text": "rumor2", "knower_npcs": ["B"]},
        ],
    }]})
    router = _make_router([resp])
    events = await build_events_data(
        description="x", ip_canon=IPCanon(), characters=chars,
        locations=[], shared_events=[], lore_pack=LorePack(),
        llm_router=router, target_count=1, batch_size=5,
    )
    e = events[0]
    assert e.disabled is False
    assert {n for r in e.rumors for n in r.knower_npcs} == {"A", "B"}


@pytest.mark.asyncio
async def test_invalid_npc_mood_changes_keys_filtered():
    chars = [_ch("A")]
    resp = json.dumps({"events": [{
        "id": "e1", "kind": "conditional", "summary": "S",
        "trigger": {"condition_dsl": "time_after('day_3')", "probability": 1.0},
        "effects": {
            "world_state_changes": {},
            "spawn_clues": [],
            "npc_mood_changes": {"A": "紧张", "幽灵NPC": "未知"},
        },
        "rumors": [],
    }]})
    router = _make_router([resp])
    events = await build_events_data(
        description="x", ip_canon=IPCanon(), characters=chars,
        locations=[], shared_events=[], lore_pack=LorePack(),
        llm_router=router, target_count=1, batch_size=5,
    )
    assert events[0].effects.npc_mood_changes == {"A": "紧张"}


@pytest.mark.asyncio
async def test_batches_split():
    """target_count=10, batch_size=4 → 3 批 (4+4+2)"""
    chars = [_ch("A")]
    responses = [
        json.dumps({"events": [_ev_json(f"e{i}") for i in range(4)]}),
        json.dumps({"events": [_ev_json(f"e{i}") for i in range(4, 8)]}),
        json.dumps({"events": [_ev_json(f"e{i}") for i in range(8, 10)]}),
    ]
    router = _make_router(responses)
    events = await build_events_data(
        description="x", ip_canon=IPCanon(), characters=chars,
        locations=[], shared_events=[], lore_pack=LorePack(),
        llm_router=router, target_count=10, batch_size=4, concurrency=3,
    )
    assert len(events) == 10
    assert router._calls["n"] == 3


@pytest.mark.asyncio
async def test_concurrent_batches_receive_disjoint_event_focus_and_id_ranges():
    chars = [_ch(f"角色{i}") for i in range(6)]
    shared = [
        SharedEvent(id=f"history_{i}", title=f"历史{i}", summary="S", involved_npcs=[], source_passage_ids=[])
        for i in range(6)
    ]
    router = _make_router([
        json.dumps({"events": [_ev_json(f"evt_{i:03d}") for i in range(1, 4)]}),
        json.dumps({"events": [_ev_json(f"evt_{i:03d}") for i in range(4, 7)]}),
    ])

    await build_events_data(
        description="x",
        ip_canon=IPCanon(),
        characters=chars,
        locations=[],
        shared_events=shared,
        lore_pack=LorePack(),
        llm_router=router,
        target_count=6,
        batch_size=3,
        concurrency=2,
    )

    assert "历史0" in router._prompts[0] and "历史3" not in router._prompts[0]
    assert "evt_001, evt_002, evt_003" in router._prompts[0]
    assert "历史3" in router._prompts[1] and "历史0" not in router._prompts[1]
    assert "evt_004, evt_005, evt_006" in router._prompts[1]


@pytest.mark.asyncio
async def test_single_batch_failure_isolates():
    chars = [_ch("A")]
    fake = MagicMock()
    idx = {"n": 0}

    async def selective(*, messages, tools, system, max_tokens):
        i = idx["n"]
        idx["n"] += 1
        if i == 0:
            yield {"type": "text_delta", "text":
                json.dumps({"events": [_ev_json(f"e{j}") for j in range(3)]})}
        else:
            raise RuntimeError("LLM fail")
            yield

    fake.stream_with_tools = selective

    events = await build_events_data(
        description="x", ip_canon=IPCanon(), characters=chars,
        locations=[], shared_events=[], lore_pack=LorePack(),
        llm_router=fake, target_count=6, batch_size=3,
    )
    assert len(events) == 3  # 第二批失败


@pytest.mark.asyncio
async def test_dedup_by_id():
    chars = [_ch("A")]
    resp1 = json.dumps({"events": [_ev_json("dup"), _ev_json("a1")]})
    resp2 = json.dumps({"events": [_ev_json("dup"), _ev_json("a2")]})
    router = _make_router([resp1, resp2])
    events = await build_events_data(
        description="x", ip_canon=IPCanon(), characters=chars,
        locations=[], shared_events=[], lore_pack=LorePack(),
        llm_router=router, target_count=4, batch_size=2,
    )
    ids = [e.id for e in events]
    assert ids.count("dup") == 1
    assert len(ids) == 4
    assert len(set(ids)) == 4


@pytest.mark.asyncio
async def test_llm_failure_returns_empty():
    fake = MagicMock()

    async def boom(*, messages, tools, system, max_tokens):
        raise RuntimeError("x")
        yield

    fake.stream_with_tools = boom
    events = await build_events_data(
        description="x", ip_canon=IPCanon(), characters=[_ch("A")],
        locations=[], shared_events=[], lore_pack=LorePack(),
        llm_router=fake, target_count=3,
    )
    assert events == []
