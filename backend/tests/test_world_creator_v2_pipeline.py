"""Integration tests for WorldCreatorAgentV2 complete 12-stage pipeline.

All builders are mocked — these tests verify pipeline structure, event ordering,
concurrency, record_intermediate calls, and result payload shape.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas.research_pack import Passage
from services.world_creator_agent_v2 import WorldCreatorAgentV2


# Existing pipeline-shape tests use minimal mock fixtures (1 character, []
# events) that pre-date the 2026-05-24 fail-fast gates. Lower the
# thresholds here so the shape assertions still run; the gate behavior
# itself is covered in tests/test_pipeline_fail_fast.py.
@pytest.fixture(autouse=True)
def _lower_fail_fast_thresholds(monkeypatch):
    monkeypatch.setattr("services.world_creator_agent_v2._MIN_CHARACTERS", 1)
    monkeypatch.setattr("services.world_creator_agent_v2._MIN_EVENTS_DATA", 0)
    monkeypatch.setattr("services.world_creator_agent_v2._MIN_SCRIPT_ENDINGS", 0)


def _build_v2_agent_with_mocks():
    """Construct v2 agent with all dependencies mocked."""
    fake_llm = MagicMock()

    async def fake_stream(*, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": "{}"}

    fake_llm.stream_with_tools = fake_stream

    fake_broker = MagicMock()
    fake_broker.collect_passages = AsyncMock(return_value=[])
    fake_broker.summarize_passages = AsyncMock(return_value="")

    # Use image_gen=None so _run_images takes the fast placeholder path without
    # touching image_storage (which would require OSS credentials in tests).
    return WorldCreatorAgentV2(
        llm=fake_llm,
        image_gen=None,
        broker=fake_broker,
    )


@pytest.mark.asyncio
async def test_world_base_does_not_stack_transport_retry(monkeypatch):
    class APITimeoutError(Exception):
        pass

    agent = _build_v2_agent_with_mocks()
    agent._last_ip_pack = None
    agent._fidelity_mode = "none"
    agent._stage_errors = {}
    collect = AsyncMock(side_effect=APITimeoutError("router exhausted"))
    monkeypatch.setattr("services.world_creator_agent_v2._collect_stream_text", collect)
    monkeypatch.setattr(
        agent,
        "_resolve_world_name",
        AsyncMock(return_value="兜底世界"),
    )

    result = await agent._generate_world_base("desc", "genre", "era")

    assert collect.await_count == 1
    assert result["name"] == "兜底世界"


@pytest.mark.asyncio
async def test_world_base_retries_unparseable_json_once(monkeypatch):
    agent = _build_v2_agent_with_mocks()
    agent._last_ip_pack = None
    agent._fidelity_mode = "none"
    agent._stage_errors = {}
    collect = AsyncMock(side_effect=[
        "not-json",
        json.dumps({"name": "候选", "locations": [{"name": "地点"}]}),
    ])
    monkeypatch.setattr("services.world_creator_agent_v2._collect_stream_text", collect)
    monkeypatch.setattr(
        agent,
        "_resolve_world_name",
        AsyncMock(return_value="有效世界"),
    )

    result = await agent._generate_world_base("desc", "genre", "era")

    assert collect.await_count == 2
    assert result["name"] == "有效世界"


@pytest.mark.asyncio
async def test_character_detail_builder_receives_only_supported_contract(monkeypatch):
    """Scale belongs to roster planning, not the character-detail builder API."""
    from schemas.character_v2 import Character, CharacterRosterEntry
    from schemas.research_pack import IPCanon, ResearchPack
    from schemas.world_generation import WorldSpec, derive_scale_plan

    agent = _build_v2_agent_with_mocks()
    agent._world_spec = WorldSpec(
        generation_run_id="run-1",
        description="desc",
        scale=derive_scale_plan(canon_character_count=24),
    )
    agent._last_ip_pack = None
    agent._fidelity_mode = "none"
    builder = AsyncMock(return_value=[Character(name="甄嬛", personality="谨慎")])
    monkeypatch.setattr(
        "services.world_creator_agent_v2.build_characters_in_batches", builder
    )

    events = [
        event
        async for event in agent._run_characters(
            "desc",
            IPCanon(),
            [CharacterRosterEntry(name="甄嬛", role_tag="主角")],
            [],
            ResearchPack(summary="", passages=[], ip_canon=IPCanon()),
        )
    ]

    assert events[-1]["code"] == "completed"
    assert "scale_plan" not in builder.await_args.kwargs
    assert builder.await_args.kwargs["batch_size"] == 6


@pytest.mark.asyncio
async def test_events_builder_uses_three_entry_batches(monkeypatch):
    from schemas.lore_pack import LorePack
    from schemas.research_pack import IPCanon
    from schemas.world_generation import WorldSpec, derive_scale_plan

    agent = _build_v2_agent_with_mocks()
    agent._world_spec = WorldSpec(
        generation_run_id="run-events",
        description="desc",
        scale=derive_scale_plan(canon_character_count=24),
    )
    builder = AsyncMock(return_value=[])
    monkeypatch.setattr("services.world_creator_agent_v2.build_events_data", builder)

    events = [
        event
        async for event in agent._run_events_data(
            "desc", IPCanon(), [], [], [], LorePack()
        )
    ]

    assert events[-1]["code"] == "completed"
    assert builder.await_args.kwargs["target_count"] == 12
    assert builder.await_args.kwargs["batch_size"] == 3


@pytest.mark.asyncio
async def test_ip_research_uses_routed_broker_web_searcher(monkeypatch):
    """IP research must reuse the admin-routed searcher, never legacy GROK_* env."""
    routed_web_searcher = object()
    broker = MagicMock()
    broker.tavily = None
    broker.web_searcher = routed_web_searcher
    agent = WorldCreatorAgentV2(llm=object(), image_gen=None, broker=broker)
    agent._fidelity_mode = "strict"
    agent._pre_recognition = SimpleNamespace(
        kind="known_ip",
        ip_name="测试作品",
        ip_type="novel",
    )
    agent._draft_id = None

    pack = MagicMock()
    pack.ip_name = "测试作品"
    pack.characters = []
    pack.places = []
    pack.passages = [
        Passage(id="p1", text="source", source="grok_search", tags=["citation:https://example.com"])
    ]
    pack.must_have_character_names.return_value = ["主角"]
    pack.model_dump.return_value = {}
    captured: dict[str, object] = {}

    async def fake_build_ip_knowledge_pack(**kwargs):
        captured.update(kwargs)
        return pack

    monkeypatch.setattr(
        "services.ip_research_pipeline.build_ip_knowledge_pack",
        fake_build_ip_knowledge_pack,
    )

    events = [event async for event in agent._run_ip_research()]

    assert captured["grok_provider"] is routed_web_searcher
    assert events[-1]["phase"] == "ip_research"
    assert events[-1]["code"] == "completed"


@pytest.mark.asyncio
async def test_strict_ip_research_failure_stops_before_generation(monkeypatch):
    from services.ip_research_pipeline import IPPackUnderfilledError

    broker = MagicMock()
    broker.tavily = None
    broker.web_searcher = object()
    agent = WorldCreatorAgentV2(llm=object(), image_gen=None, broker=broker)
    agent._fidelity_mode = "strict"
    agent._pre_recognition = SimpleNamespace(
        kind="known_ip",
        ip_name="测试作品",
        ip_type="novel",
    )
    agent._draft_id = None

    async def fail_build(**_kwargs):
        raise IPPackUnderfilledError("测试作品", 2, 100)

    monkeypatch.setattr(
        "services.ip_research_pipeline.build_ip_knowledge_pack",
        fail_build,
    )
    events: list[dict] = []

    with pytest.raises(IPPackUnderfilledError):
        async for event in agent._run_ip_research():
            events.append(event)

    assert any(event.get("code") == "ip_pack_underfilled" for event in events)
    assert not any(event.get("code") == "completed" for event in events)


@pytest.mark.asyncio
async def test_strict_ip_research_without_evidence_stops(monkeypatch):
    broker = MagicMock()
    broker.tavily = None
    broker.web_searcher = object()
    agent = WorldCreatorAgentV2(llm=object(), image_gen=None, broker=broker)
    agent._fidelity_mode = "strict"
    agent._pre_recognition = SimpleNamespace(
        kind="known_ip",
        ip_name="测试作品",
        ip_type="novel",
    )
    agent._draft_id = None
    pack = MagicMock()
    pack.ip_name = "测试作品"
    pack.characters = [object()] * 12
    pack.places = []
    pack.passages = []
    pack.must_have_character_names.return_value = ["主角"]

    async def build_without_evidence(**_kwargs):
        return pack

    monkeypatch.setattr(
        "services.ip_research_pipeline.build_ip_knowledge_pack",
        build_without_evidence,
    )
    events: list[dict] = []

    with pytest.raises(RuntimeError, match="no source evidence"):
        async for event in agent._run_ip_research():
            events.append(event)

    assert any(event.get("code") == "ip_pack_no_evidence" for event in events)
    assert not any(event.get("code") == "completed" for event in events)


@pytest.mark.asyncio
async def test_strict_ip_research_without_citations_stops(monkeypatch):
    broker = MagicMock()
    broker.tavily = None
    broker.web_searcher = object()
    agent = WorldCreatorAgentV2(llm=object(), image_gen=None, broker=broker)
    agent._fidelity_mode = "strict"
    agent._pre_recognition = SimpleNamespace(kind="known_ip", ip_name="测试作品", ip_type="novel")
    agent._draft_id = None
    pack = MagicMock()
    pack.ip_name = "测试作品"
    pack.characters = [object()] * 12
    pack.places = []
    pack.passages = [Passage(id="p1", text="uncited", source="grok_search", tags=["query:test"])]
    pack.must_have_character_names.return_value = ["主角"]

    async def build_without_citations(**_kwargs):
        return pack

    monkeypatch.setattr("services.ip_research_pipeline.build_ip_knowledge_pack", build_without_citations)
    events: list[dict] = []
    with pytest.raises(RuntimeError, match="no citations"):
        async for event in agent._run_ip_research():
            events.append(event)

    assert any(event.get("code") == "ip_pack_no_citations" for event in events)


@pytest.mark.asyncio
async def test_loose_ip_research_failure_degrades_with_warning(monkeypatch):
    broker = MagicMock()
    broker.tavily = None
    broker.web_searcher = object()
    agent = WorldCreatorAgentV2(llm=object(), image_gen=None, broker=broker)
    agent._fidelity_mode = "loose"
    agent._pre_recognition = SimpleNamespace(
        kind="known_ip",
        ip_name="测试作品",
        ip_type="novel",
    )
    agent._draft_id = None

    async def fail_build(**_kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(
        "services.ip_research_pipeline.build_ip_knowledge_pack",
        fail_build,
    )
    events = [event async for event in agent._run_ip_research()]

    assert any(event.get("code") == "ip_pack_build_failed" for event in events)
    assert events[-1]["code"] == "completed"
    assert events[-1]["meta"]["characters"] == 0


@pytest.mark.asyncio
async def test_pipeline_emits_all_stages_in_order():
    """v2 流跑通 12 阶段，每阶段 emit started + completed。"""
    agent = _build_v2_agent_with_mocks()

    from schemas.character_v2 import Character, CharacterRosterEntry
    from schemas.lore_pack import LorePack
    from schemas.research_pack import IPCanon, ResearchPack
    from schemas.shared_events import RelationsPack

    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(
                return_value=ResearchPack(
                    summary="", passages=[], ip_canon=IPCanon()
                )
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_dimensions",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_pack",
            AsyncMock(return_value=LorePack(dimensions=[])),
        ),
        patch(
            "services.world_creator_agent_v2.build_character_roster",
            AsyncMock(
                return_value=[
                    CharacterRosterEntry(
                        name="A", role_tag="主角", is_image_target=True
                    )
                ]
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_characters_in_batches",
            AsyncMock(
                return_value=[
                    Character(name="A", personality="p", is_image_target=True)
                ]
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_relations_pack",
            MagicMock(return_value=RelationsPack(relations_by_npc={})),
        ),
        patch(
            "services.world_creator_agent_v2.build_events_data",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.light_critic_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.moderate_world_payload",
            AsyncMock(return_value=[]),
        ),
    ):
        events = []
        async for event in agent.create_world("desc", "genre", "era"):
            events.append(event)

    # Extract all 'started' phase names
    phases = []
    for e in events:
        if e.get("type") == "progress" and e.get("data", e).get("code") == "started":
            phases.append(e.get("data", e).get("phase", e.get("phase")))

    # Handle both flat and nested data formats
    phases_flat = []
    for e in events:
        if e.get("type") == "progress":
            meta = e.get("meta", {})
            if meta.get("code") == "started" or e.get("code") == "started":
                phases_flat.append(e.get("phase", meta.get("phase", "")))

    all_phases = set(phases) | set(phases_flat)

    expected_phases = [
        "research_pack",
        "world_base",
        "lore_dimensions",
        "character_roster",
        "lore_pack",
        "characters",
        "shared_events",
        "relations_pack",
        "events_data",
        "playable",
        "critic",
        "images",
        "validating",
    ]
    for p in expected_phases:
        assert p in all_phases, f"missing phase {p} in {all_phases}"


@pytest.mark.asyncio
async def test_pipeline_emits_result_with_all_v2_fields():
    agent = _build_v2_agent_with_mocks()

    from schemas.character_v2 import Character, CharacterRosterEntry
    from schemas.lore_pack import LorePack
    from schemas.research_pack import IPCanon, ResearchPack
    from schemas.shared_events import RelationsPack

    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(
                return_value=ResearchPack(
                    summary="s", passages=[], ip_canon=IPCanon()
                )
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_dimensions",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_pack",
            AsyncMock(return_value=LorePack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_character_roster",
            AsyncMock(
                return_value=[
                    CharacterRosterEntry(
                        name="A", role_tag="主角", is_image_target=True
                    )
                ]
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_characters_in_batches",
            AsyncMock(
                return_value=[
                    Character(name="A", personality="p", is_image_target=True)
                ]
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_relations_pack",
            MagicMock(return_value=RelationsPack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_events_data",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.light_critic_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.moderate_world_payload",
            AsyncMock(return_value=[]),
        ),
    ):
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    result = next((e for e in events if e.get("type") == "result"), None)
    assert result is not None
    # result_event spreads data into top-level fields
    payload = result
    # Key v2 fields
    for key in (
        "research_pack",
        "lore_pack",
        "shared_events",
        "events_data",
        "world_characters",
        "playable",
        "quality_warnings",
    ):
        assert key in payload, f"result payload missing {key}"


@pytest.mark.asyncio
async def test_pipeline_handles_research_pack_failure_gracefully():
    """research_pack 失败 → 后续阶段以空 ResearchPack 继续，不 crash。"""
    agent = _build_v2_agent_with_mocks()

    from schemas.character_v2 import Character, CharacterRosterEntry
    from schemas.lore_pack import LorePack
    from schemas.shared_events import RelationsPack

    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(side_effect=RuntimeError("research failed")),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_dimensions",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_pack",
            AsyncMock(return_value=LorePack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_character_roster",
            AsyncMock(
                return_value=[
                    CharacterRosterEntry(
                        name="A", role_tag="r", is_image_target=False
                    )
                ]
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_characters_in_batches",
            AsyncMock(return_value=[Character(name="A", personality="p")]),
        ),
        patch(
            "services.world_creator_agent_v2.build_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_relations_pack",
            MagicMock(return_value=RelationsPack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_events_data",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.light_critic_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.moderate_world_payload",
            AsyncMock(return_value=[]),
        ),
    ):
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    # Should flow all the way to done
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_pipeline_record_intermediate_called_per_stage(monkeypatch):
    """每阶段 completed 后 record_intermediate 被调用。"""
    fake_service = MagicMock()
    fake_service.record_intermediate = AsyncMock()

    fake_llm = MagicMock()

    async def fake_stream(*, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": "{}"}

    fake_llm.stream_with_tools = fake_stream
    fake_broker = MagicMock()
    fake_broker.collect_passages = AsyncMock(return_value=[])
    fake_broker.summarize_passages = AsyncMock(return_value="")

    agent = WorldCreatorAgentV2(
        llm=fake_llm,
        image_gen=None,  # placeholder path; no OSS credentials in tests
        broker=fake_broker,
        task_service=fake_service,
        task_id="t1",
    )

    from schemas.character_v2 import Character, CharacterRosterEntry
    from schemas.lore_pack import LorePack
    from schemas.research_pack import IPCanon, ResearchPack
    from schemas.shared_events import RelationsPack

    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(
                return_value=ResearchPack(
                    summary="", passages=[], ip_canon=IPCanon()
                )
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_dimensions",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_pack",
            AsyncMock(return_value=LorePack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_character_roster",
            AsyncMock(
                return_value=[
                    CharacterRosterEntry(
                        name="A", role_tag="r", is_image_target=True
                    )
                ]
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_characters_in_batches",
            AsyncMock(
                return_value=[
                    Character(name="A", personality="p", is_image_target=True)
                ]
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_relations_pack",
            MagicMock(return_value=RelationsPack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_events_data",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.light_critic_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.moderate_world_payload",
            AsyncMock(return_value=[]),
        ),
    ):
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    # record_intermediate should be called at least 6 times
    assert fake_service.record_intermediate.call_count >= 6

    # Check key phases are represented
    called_phases = set()
    for call in fake_service.record_intermediate.call_args_list:
        # record_intermediate(task_id, phase=..., snapshot=...)
        kw = call.kwargs
        args = call.args
        phase = kw.get("phase") or (args[1] if len(args) > 1 else None)
        if phase:
            called_phases.add(phase)

    expected = {"research_pack", "world_base", "lore_pack", "characters"}
    assert expected.issubset(called_phases), (
        f"expected phases not all covered, got {called_phases}"
    )


@pytest.mark.asyncio
async def test_pipeline_concurrent_c1_c2_stages():
    """C1 (lore_dimensions) 和 C2 (character_roster) 应并发，不串行。"""
    agent = _build_v2_agent_with_mocks()

    call_order: list[str] = []

    async def slow_lore(*args, **kw):
        call_order.append("lore_dim_start")
        await asyncio.sleep(0.05)
        call_order.append("lore_dim_done")
        return []

    async def slow_roster(*args, **kw):
        call_order.append("roster_start")
        await asyncio.sleep(0.05)
        call_order.append("roster_done")
        return []

    from schemas.lore_pack import LorePack
    from schemas.research_pack import IPCanon, ResearchPack
    from schemas.shared_events import RelationsPack

    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(
                return_value=ResearchPack(
                    summary="", passages=[], ip_canon=IPCanon()
                )
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_dimensions",
            side_effect=slow_lore,
        ),
        patch(
            "services.world_creator_agent_v2.build_character_roster",
            side_effect=slow_roster,
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_pack",
            AsyncMock(return_value=LorePack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_characters_in_batches",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_relations_pack",
            MagicMock(return_value=RelationsPack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_events_data",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.light_critic_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.moderate_world_payload",
            AsyncMock(return_value=[]),
        ),
    ):
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    # If concurrent: roster_start appears before lore_dim_done
    if "roster_start" in call_order and "lore_dim_done" in call_order:
        roster_start_idx = call_order.index("roster_start")
        lore_done_idx = call_order.index("lore_dim_done")
        assert roster_start_idx < lore_done_idx, (
            f"C1/C2 ran serially: {call_order}"
        )


@pytest.mark.asyncio
async def test_pipeline_quality_warnings_aggregated():
    """所有 critic warnings 都应汇总到 result.payload.quality_warnings。"""
    agent = _build_v2_agent_with_mocks()

    from schemas.character_v2 import Character, CharacterRosterEntry
    from schemas.lore_pack import LorePack
    from schemas.research_pack import IPCanon, ResearchPack
    from schemas.shared_events import RelationsPack

    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(
                return_value=ResearchPack(
                    summary="", passages=[], ip_canon=IPCanon()
                )
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_dimensions",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_pack",
            AsyncMock(return_value=LorePack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_character_roster",
            AsyncMock(
                return_value=[
                    CharacterRosterEntry(
                        name="A", role_tag="r", is_image_target=False
                    )
                ]
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_characters_in_batches",
            AsyncMock(return_value=[Character(name="A", personality="p")]),
        ),
        patch(
            "services.world_creator_agent_v2.build_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_relations_pack",
            MagicMock(return_value=RelationsPack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_events_data",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.light_critic_shared_events",
            AsyncMock(return_value=["se_warning_1"]),
        ),
        patch(
            "services.world_creator_agent_v2.moderate_world_payload",
            AsyncMock(return_value=["moderation_flag:explicit"]),
        ),
    ):
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    result = next((e for e in events if e.get("type") == "result"), None)
    assert result is not None
    warnings = result.get("quality_warnings", [])
    # H2/H2.5（lore/事件/角色一致性软评分）已移到 done 后的异步质量打分器，世界主流程
    # 只保留确定性安全网 + moderation。这里验证 moderation warning 仍汇总到
    # quality_warnings（其余 LLM 软评分不再走同步路径）。
    assert "moderation_flag:explicit" in warnings


@pytest.mark.asyncio
async def test_pipeline_playable_filtered_from_image_targets():
    """playable 应该是 is_image_target=true 的子集。"""
    agent = _build_v2_agent_with_mocks()

    from schemas.character_v2 import Character, CharacterRosterEntry
    from schemas.lore_pack import LorePack
    from schemas.research_pack import IPCanon, ResearchPack
    from schemas.shared_events import RelationsPack

    chars = [
        Character(
            name="A", personality="p", is_image_target=True, role_tag="主角"
        ),
        Character(
            name="B", personality="p", is_image_target=False, role_tag="路人"
        ),
        Character(
            name="C", personality="p", is_image_target=True, role_tag="配角"
        ),
    ]

    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(
                return_value=ResearchPack(
                    summary="", passages=[], ip_canon=IPCanon()
                )
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_dimensions",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_lore_pack",
            AsyncMock(return_value=LorePack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_character_roster",
            AsyncMock(
                return_value=[
                    CharacterRosterEntry(
                        name=c.name,
                        role_tag=c.role_tag,
                        is_image_target=c.is_image_target,
                    )
                    for c in chars
                ]
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_characters_in_batches",
            AsyncMock(return_value=chars),
        ),
        patch(
            "services.world_creator_agent_v2.build_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.build_relations_pack",
            MagicMock(return_value=RelationsPack()),
        ),
        patch(
            "services.world_creator_agent_v2.build_events_data",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.light_critic_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.world_creator_agent_v2.moderate_world_payload",
            AsyncMock(return_value=[]),
        ),
    ):
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    result = next((e for e in events if e.get("type") == "result"), None)
    assert result is not None
    playable = result.get("playable", [])
    playable_names = {p["name"] for p in playable}
    assert playable_names == {"A", "C"}
    assert "B" not in playable_names


# =============================================================================
# Stage I image tests
# =============================================================================


def _make_builder_patches(chars):
    """Return list of patch context managers for all builder functions."""
    from schemas.character_v2 import CharacterRosterEntry
    from schemas.lore_pack import LorePack
    from schemas.research_pack import IPCanon, ResearchPack
    from schemas.shared_events import RelationsPack

    return [
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(return_value=ResearchPack(summary="", passages=[], ip_canon=IPCanon())),
        ),
        patch("services.world_creator_agent_v2.build_lore_dimensions", AsyncMock(return_value=[])),
        patch("services.world_creator_agent_v2.build_lore_pack", AsyncMock(return_value=LorePack())),
        patch(
            "services.world_creator_agent_v2.build_character_roster",
            AsyncMock(
                return_value=[
                    CharacterRosterEntry(
                        name=c.name,
                        role_tag=c.role_tag or "角色",
                        is_image_target=c.is_image_target,
                    )
                    for c in chars
                ]
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_characters_in_batches",
            AsyncMock(return_value=chars),
        ),
        patch("services.world_creator_agent_v2.build_shared_events", AsyncMock(return_value=[])),
        patch(
            "services.world_creator_agent_v2.build_relations_pack",
            MagicMock(return_value=RelationsPack()),
        ),
        patch("services.world_creator_agent_v2.build_events_data", AsyncMock(return_value=[])),
        patch(
            "services.world_creator_agent_v2.light_critic_shared_events",
            AsyncMock(return_value=[]),
        ),
        patch("services.world_creator_agent_v2.moderate_world_payload", AsyncMock(return_value=[])),
    ]


def _apply_patches(stack, patches):
    """Enter all patch context managers via an ExitStack."""
    for p in patches:
        stack.enter_context(p)


class _SequencedTextLLM:
    def __init__(self, outputs: list[dict]):
        self.outputs = [json.dumps(output, ensure_ascii=False) for output in outputs]

    async def stream_with_tools(self, **_kwargs):
        if not self.outputs:
            raise AssertionError("LLM called more times than expected")
        yield {"type": "text_delta", "text": self.outputs.pop(0)}


def _stage_payload(label: str) -> dict:
    return {
        "has_arc": True,
        "stages": [
            {
                "milestone": f"{label}一段",
                "subtitle": "入局",
                "tagline": "从这里开始",
                "start_location": "靖安司",
                "opening_framing": "你已经入局。",
                "known_relations": [],
            },
            {
                "milestone": f"{label}二段",
                "subtitle": "推进",
                "tagline": "局势升级",
                "start_location": "靖安司",
                "opening_framing": "局势已经升级。",
                "known_relations": [],
            },
        ],
    }


@pytest.mark.asyncio
async def test_free_start_stages_prioritizes_primary_playable_characters():
    """Regression: top playable protagonists are generated in one batch."""
    from schemas.character_v2 import Character

    fake_llm = _SequencedTextLLM([
        {
            "characters": [
                {"character_name": name, **_stage_payload(name)}
                for name in ("张小敬", "李必", "徐宾")
            ]
        },
    ])
    agent = WorldCreatorAgentV2(llm=fake_llm, image_gen=None, broker=None)
    characters = [
        Character(name="张小敬", role_tag="主角", personality="死囚入局", initial_location="靖安司"),
        Character(name="李必", role_tag="主角", personality="靖安司少令", initial_location="靖安司"),
        Character(name="徐宾", role_tag="核心", personality="算学档案", initial_location="靖安司"),
        Character(name="元载", role_tag="权臣", personality="官场上行", initial_location="大理寺"),
        Character(name="龙波", role_tag="反派", personality="复仇", initial_location="怀远坊"),
    ]
    playable = [
        {"name": "张小敬", "role_tag": "戴罪追凶", "description": "死囚入局"},
        {"name": "李必", "role_tag": "靖安司少令", "description": "坐镇靖安司"},
        {"name": "徐宾", "role_tag": "算学档案", "description": "档案枢纽"},
        {"name": "元载", "role_tag": "大理寺官员", "description": "官场上行"},
        {"name": "龙波", "role_tag": "狼卫首领", "description": "复仇"},
    ]

    events = []
    async for event in agent._run_free_start_stages(
        "长安十二时辰", "历史悬疑", "唐朝", characters, playable,
        [{"name": "靖安司"}, {"name": "大理寺"}, {"name": "怀远坊"}],
    ):
        events.append(event)

    assert agent._last_free_start_stages is not None
    names = [entry["character_name"] for entry in agent._last_free_start_stages["characters"]]
    assert names == ["张小敬", "李必", "徐宾"]
    assert "元载" not in names
    assert "龙波" not in names
    assert not [e for e in events if e.get("type") == "warning"]
    assert fake_llm.outputs == []


@pytest.mark.asyncio
async def test_free_start_stages_warns_when_primary_character_missing():
    from schemas.character_v2 import Character

    fake_llm = _SequencedTextLLM([
        {"characters": [{"character_name": "张小敬", "has_arc": False, "stages": []}]},
        {"characters": [{"character_name": "张小敬", "has_arc": False, "stages": []}]},
    ])
    agent = WorldCreatorAgentV2(llm=fake_llm, image_gen=None, broker=None)
    characters = [
        Character(name="张小敬", role_tag="主角", personality="死囚入局", initial_location="靖安司"),
    ]
    playable = [{"name": "张小敬", "role_tag": "戴罪追凶", "description": "死囚入局"}]

    events = []
    async for event in agent._run_free_start_stages(
        "长安十二时辰", "历史悬疑", "唐朝", characters, playable, [{"name": "靖安司"}],
    ):
        events.append(event)

    warnings = [
        e for e in events
        if e.get("type") == "warning" and e.get("code") == "primary_character_missing"
    ]
    assert warnings
    assert warnings[0]["meta"]["missing_primary"] == ["张小敬"]


@pytest.mark.asyncio
async def test_images_stage_skips_when_no_image_gen():
    """image_gen=None → 所有图片用 placeholder，不调外部服务，流程不中断。"""
    from schemas.character_v2 import Character
    from services.image_storage import IMAGE_PLACEHOLDER_URL

    fake_llm = MagicMock()

    async def fake_stream(*, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": "{}"}

    fake_llm.stream_with_tools = fake_stream
    fake_broker = MagicMock()
    fake_broker.collect_passages = AsyncMock(return_value=[])
    fake_broker.summarize_passages = AsyncMock(return_value="")

    agent = WorldCreatorAgentV2(llm=fake_llm, image_gen=None, broker=fake_broker)

    chars = [
        Character(name="Alice", personality="brave", is_image_target=True, role_tag="主角"),
        Character(name="Bob", personality="sly", is_image_target=False, role_tag="路人"),
    ]

    with contextlib.ExitStack() as stack:
        _apply_patches(stack, _make_builder_patches(chars))
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    result = next((e for e in events if e.get("type") == "result"), None)
    assert result is not None, "no result event emitted"
    assert result.get("cover_image") == IMAGE_PLACEHOLDER_URL
    assert result.get("hero_image") == IMAGE_PLACEHOLDER_URL
    # only image_target chars get an entry
    char_images = result.get("character_images", {})
    assert "Alice" in char_images
    assert char_images["Alice"] == IMAGE_PLACEHOLDER_URL
    assert "Bob" not in char_images

    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_images_stage_calls_generator_for_target_npcs():
    """cover_brief 派生成功 → 1 张 hero (21:9) + N 张 portrait (2:3) — cover 由 hero 服务端裁剪。"""
    from llm.base import ImageResult
    from schemas.character_v2 import Character

    fake_llm = MagicMock()

    # cover_brief_helper expects JSON describing world + characters. We return
    # a minimal-but-valid response so the helper produces a CoverBrief that
    # the images stage can drive prompts off of.
    helper_response = {
        "world_name_english": "Test World",
        "characters": {
            "A": {"name_english": "A", "mood_anchor": "stoic",
                  "gender": "男", "age_band": "青年", "role_class": "工人"},
            "B": {"name_english": "B", "mood_anchor": "wary",
                  "gender": "女", "age_band": "青年", "role_class": "学生"},
        },
    }

    async def fake_stream(*, messages, tools, system, max_tokens, **kwargs):
        # cover_brief_helper does plain JSON (no tools); all other LLM calls
        # in the pipeline either ignore the response or get faked elsewhere.
        yield {"type": "text_delta", "text": json.dumps(helper_response)}

    fake_llm.stream_with_tools = fake_stream
    fake_broker = MagicMock()
    fake_broker.collect_passages = AsyncMock(return_value=[])
    fake_broker.summarize_passages = AsyncMock(return_value="")

    # ImageResult must carry usable bytes for the cover crop step (PIL needs real bytes).
    # We patch materialize_image_bytes + crop_to_aspect_ratio so we don't depend on Pillow data.
    fake_image_gen = MagicMock()
    fake_image_gen.generate_image = AsyncMock(
        return_value=ImageResult(url="/static/generated/image.png")
    )

    agent = WorldCreatorAgentV2(llm=fake_llm, image_gen=fake_image_gen, broker=fake_broker)

    chars = [
        Character(name="A", personality="p1", is_image_target=True, role_tag="主角"),
        Character(name="B", personality="p2", is_image_target=True, role_tag="配角"),
        Character(name="C", personality="p3", is_image_target=False, role_tag="路人"),
    ]

    fake_storage = MagicMock()
    fake_storage.save = AsyncMock(return_value="/static/generated/cover.jpg")

    # Patch save_generated_image_result, get_image_storage, and the cropper helpers
    # so we don't touch disk or require real image bytes.
    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch(
                "services.world_creator_agent_v2.get_image_storage",
                return_value=fake_storage,
            )
        )
        stack.enter_context(
            patch(
                "services.world_creator_agent_v2.save_generated_image_result",
                AsyncMock(return_value="/static/generated/image.png"),
            )
        )
        stack.enter_context(
            patch(
                "services.image_cropper.materialize_image_bytes",
                AsyncMock(return_value=b"\x00" * 32),
            )
        )
        stack.enter_context(
            patch(
                "services.image_cropper.crop_to_aspect_ratio",
                MagicMock(return_value=b"\x00" * 32),
            )
        )
        _apply_patches(stack, _make_builder_patches(chars))
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    # New shape (cover independent gen): 1 hero (21:9) + 1 cover (3:2) +
    # N portrait calls (2:3) for A and B. Cover is its own generate_image call,
    # no longer server-cropped from hero (crop only runs as fallback).
    target_count = sum(1 for c in chars if c.is_image_target)
    assert fake_image_gen.generate_image.call_count == 2 + target_count, (
        f"expected {2 + target_count} calls, got {fake_image_gen.generate_image.call_count}"
    )

    # Inspect call aspect ratios: 1 × 21:9 (hero) + 1 × 3:2 (cover) + N × 2:3 (portraits)
    aspect_ratios = [
        call.kwargs.get("aspect_ratio")
        for call in fake_image_gen.generate_image.call_args_list
    ]
    assert aspect_ratios.count("21:9") == 1, f"expected one 21:9 hero call, got {aspect_ratios}"
    assert aspect_ratios.count("3:2") == 1, f"expected one 3:2 cover call, got {aspect_ratios}"
    assert aspect_ratios.count("2:3") == target_count, (
        f"expected {target_count} 2:3 portrait calls, got {aspect_ratios}"
    )

    result = next((e for e in events if e.get("type") == "result"), None)
    assert result is not None
    # 新 pipeline 不再持久化 visual_brief 到 payload（每次 derive on-the-fly）
    assert "visual_brief" not in result
    # hero + cover are both raw generated urls now (no crop fallback in happy path).
    assert result.get("hero_image") == "/static/generated/image.png"
    assert result.get("cover_image") == "/static/generated/image.png"
    char_images = result.get("character_images", {})
    assert set(char_images.keys()) == {"A", "B"}
    assert "C" not in char_images


@pytest.mark.asyncio
async def test_images_fallback_to_placeholder_on_failure():
    """单张图片生成失败 → fallback placeholder，其余正常，流程不阻断。"""
    from llm.base import ImageResult
    from schemas.character_v2 import Character
    from services.image_storage import IMAGE_PLACEHOLDER_URL

    fake_llm = MagicMock()

    helper_response = {
        "world_name_english": "Test",
        "characters": {
            "X": {"name_english": "X", "mood_anchor": "tired",
                  "gender": "男", "age_band": "中年", "role_class": "工人"},
        },
    }

    async def fake_stream(*, messages, tools, system, max_tokens, **kwargs):
        yield {"type": "text_delta", "text": json.dumps(helper_response)}

    fake_llm.stream_with_tools = fake_stream
    fake_broker = MagicMock()
    fake_broker.collect_passages = AsyncMock(return_value=[])
    fake_broker.summarize_passages = AsyncMock(return_value="")

    call_count = {"n": 0}

    async def selective_fail(prompt, *, aspect_ratio="1:1", resolution="1k"):
        call_count["n"] += 1
        # Fail the portrait call (call #3 in new shape: hero, cover, portrait).
        # Failing the cover call instead would now succeed via the hero-crop
        # fallback chain, masking the placeholder behavior we want to test.
        if aspect_ratio == "2:3":
            raise RuntimeError("Seedream 5xx")
        return ImageResult(url=f"/static/generated/img-{call_count['n']}.png")

    fake_image_gen = MagicMock()
    fake_image_gen.generate_image = selective_fail

    agent = WorldCreatorAgentV2(llm=fake_llm, image_gen=fake_image_gen, broker=fake_broker)

    chars = [
        Character(name="X", personality="q", is_image_target=True, role_tag="主角"),
    ]

    fake_storage = MagicMock()
    fake_storage.save = AsyncMock(return_value="/static/generated/cover.jpg")

    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch(
                "services.world_creator_agent_v2.get_image_storage",
                return_value=fake_storage,
            )
        )
        stack.enter_context(
            patch(
                "services.world_creator_agent_v2.save_generated_image_result",
                AsyncMock(side_effect=lambda storage, result, key: result.url),
            )
        )
        stack.enter_context(
            patch(
                "services.image_cropper.materialize_image_bytes",
                AsyncMock(return_value=b"\x00" * 32),
            )
        )
        stack.enter_context(
            patch(
                "services.image_cropper.crop_to_aspect_ratio",
                MagicMock(return_value=b"\x00" * 32),
            )
        )
        _apply_patches(stack, _make_builder_patches(chars))
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    assert events[-1]["type"] == "done", "pipeline must reach done even if image fails"

    result = next((e for e in events if e.get("type") == "result"), None)
    assert result is not None
    # At least one image should be placeholder (the failed one)
    all_images = [
        result.get("cover_image"),
        result.get("hero_image"),
    ] + list(result.get("character_images", {}).values())
    assert IMAGE_PLACEHOLDER_URL in all_images, (
        "expected at least one placeholder after failure, but none found"
    )


@pytest.mark.asyncio
async def test_generate_image_with_fallback_retries_unknown_failure(monkeypatch):
    """Unknown failures are retried once before falling back."""
    from llm.base import ImageResult
    from services import world_creator_agent_v2 as v2

    monkeypatch.setattr(v2, "_IMAGE_RETRY_BACKOFFS", (0.0, 0.0))

    class FlakyImageGen:
        def __init__(self) -> None:
            self.calls = 0

        async def generate_image(self, prompt, *, aspect_ratio="1:1", resolution="1k"):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary upstream wobble")
            return ImageResult(url="/remote/ok.png")

    image_gen = FlakyImageGen()

    with patch(
        "services.world_creator_agent_v2.save_generated_image_result",
        AsyncMock(side_effect=lambda storage, result, key: result.url),
    ):
        url, result = await v2._generate_image_with_fallback(
            image_gen,
            ["prompt"],
            aspect_ratio="3:2",
            storage=MagicMock(),
            storage_key="worlds/test.png",
            log_key="test",
            max_attempts=2,
        )

    assert image_gen.calls == 2
    assert url == "/remote/ok.png"
    assert result is not None


@pytest.mark.asyncio
async def test_generate_image_with_fallback_retries_timeout(monkeypatch):
    """A hung attempt is cut off by the image timeout and retried."""
    from llm.base import ImageResult
    from config import settings
    from services import world_creator_agent_v2 as v2

    monkeypatch.setattr(settings, "image_generation_timeout_seconds", 0.01)
    monkeypatch.setattr(v2, "_IMAGE_RETRY_BACKOFFS", (0.0, 0.0))

    class SlowThenOkImageGen:
        def __init__(self) -> None:
            self.calls = 0

        async def generate_image(self, prompt, *, aspect_ratio="1:1", resolution="1k"):
            self.calls += 1
            if self.calls == 1:
                await asyncio.Future()
            return ImageResult(url="/remote/after-timeout.png")

    image_gen = SlowThenOkImageGen()

    with patch(
        "services.world_creator_agent_v2.save_generated_image_result",
        AsyncMock(side_effect=lambda storage, result, key: result.url),
    ):
        url, _result = await v2._generate_image_with_fallback(
            image_gen,
            ["prompt"],
            aspect_ratio="3:2",
            storage=MagicMock(),
            storage_key="worlds/test.png",
            log_key="test",
            max_attempts=2,
        )

    assert image_gen.calls == 2
    assert url == "/remote/after-timeout.png"


@pytest.mark.asyncio
async def test_generate_image_with_fallback_does_not_regenerate_after_storage_failure(monkeypatch):
    """OSS retries bytes internally; exhausting them must not spend another image call."""
    from llm.base import ImageResult
    from services import world_creator_agent_v2 as v2
    from services.image_storage import IMAGE_PLACEHOLDER_URL, ImageStorageUploadError

    monkeypatch.setattr(v2, "_IMAGE_RETRY_BACKOFFS", (0.0, 0.0))

    class ImageGen:
        def __init__(self) -> None:
            self.calls = 0

        async def generate_image(self, prompt, *, aspect_ratio="1:1", resolution="1k"):
            self.calls += 1
            return ImageResult(base64_data=b"generated-once")

    image_gen = ImageGen()
    with patch(
        "services.world_creator_agent_v2.save_generated_image_result",
        AsyncMock(side_effect=ImageStorageUploadError("OSS timeout")),
    ):
        url, result = await v2._generate_image_with_fallback(
            image_gen,
            ["prompt"],
            aspect_ratio="3:2",
            storage=MagicMock(),
            storage_key="worlds/test.png",
            log_key="test",
            max_attempts=3,
        )

    assert image_gen.calls == 1
    assert url == IMAGE_PLACEHOLDER_URL
    assert result is None


@pytest.mark.asyncio
async def test_generate_image_with_fallback_does_not_repeat_provider_placeholder(monkeypatch):
    """Provider-level placeholder means the provider already exhausted itself."""
    from llm.base import ImageResult
    from services import world_creator_agent_v2 as v2
    from services.image_storage import IMAGE_PLACEHOLDER_URL

    monkeypatch.setattr(v2, "_IMAGE_RETRY_BACKOFFS", (0.0, 0.0))

    class PlaceholderImageGen:
        def __init__(self) -> None:
            self.calls = 0

        async def generate_image(self, prompt, *, aspect_ratio="1:1", resolution="1k"):
            self.calls += 1
            return ImageResult(url=IMAGE_PLACEHOLDER_URL)

    image_gen = PlaceholderImageGen()

    with patch(
        "services.world_creator_agent_v2.save_generated_image_result",
        AsyncMock(return_value=IMAGE_PLACEHOLDER_URL),
    ):
        url, result = await v2._generate_image_with_fallback(
            image_gen,
            ["prompt"],
            aspect_ratio="3:2",
            storage=MagicMock(),
            storage_key="worlds/test.png",
            log_key="test",
            max_attempts=3,
        )

    assert image_gen.calls == 1
    assert url == IMAGE_PLACEHOLDER_URL
    assert result is None


# =============================================================================
# Subtask events tests (lore_pack / characters / events_data)
# =============================================================================


@pytest.mark.asyncio
async def test_lore_pack_emits_subtask_completed_per_dimension():
    """lore_pack 阶段完成时 emit 每维度的 subtask_completed 事件（回放模式）。"""
    from schemas.character_v2 import Character, CharacterRosterEntry
    from schemas.lore_pack import LorePack, LoreDimensionContent, LoreContentBlock
    from schemas.research_pack import IPCanon, ResearchPack
    from schemas.shared_events import RelationsPack

    agent = _build_v2_agent_with_mocks()

    # lore_pack with 3 dimensions (2 with content, 1 empty/failed)
    lore_pack_with_3_dims = LorePack(dimensions=[
        LoreDimensionContent(key="tech", name="技术", content_blocks=[LoreContentBlock(heading="h", body="b")]),
        LoreDimensionContent(key="schools", name="门派", content_blocks=[LoreContentBlock(heading="h2", body="b2")]),
        LoreDimensionContent(key="empty", name="空", content_blocks=[]),  # 失败维度
    ])

    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(return_value=ResearchPack(summary="", passages=[], ip_canon=IPCanon())),
        ),
        patch("services.world_creator_agent_v2.build_lore_dimensions", AsyncMock(return_value=[])),
        patch("services.world_creator_agent_v2.build_lore_pack", AsyncMock(return_value=lore_pack_with_3_dims)),
        patch(
            "services.world_creator_agent_v2.build_character_roster",
            AsyncMock(return_value=[CharacterRosterEntry(name="A", role_tag="r", is_image_target=False)]),
        ),
        patch(
            "services.world_creator_agent_v2.build_characters_in_batches",
            AsyncMock(return_value=[Character(name="A", personality="p")]),
        ),
        patch("services.world_creator_agent_v2.build_shared_events", AsyncMock(return_value=[])),
        patch(
            "services.world_creator_agent_v2.build_relations_pack",
            MagicMock(return_value=RelationsPack(relations_by_npc={})),
        ),
        patch("services.world_creator_agent_v2.build_events_data", AsyncMock(return_value=[])),
        patch("services.world_creator_agent_v2.light_critic_shared_events", AsyncMock(return_value=[])),
        patch("services.world_creator_agent_v2.moderate_world_payload", AsyncMock(return_value=[])),
    ):
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    # 2 subtask_completed (non-empty dims) + 1 subtask_failed (empty dim)
    lore_subtask_completed = [
        e for e in events
        if e.get("type") == "progress"
        and e.get("phase") == "lore_pack"
        and e.get("code") == "subtask_completed"
    ]
    lore_subtask_failed = [
        e for e in events
        if e.get("type") == "warning"
        and e.get("phase") == "lore_pack"
        and e.get("code") == "subtask_failed"
    ]
    assert len(lore_subtask_completed) == 2, f"expected 2 subtask_completed, got {len(lore_subtask_completed)}"
    assert len(lore_subtask_failed) == 1, f"expected 1 subtask_failed, got {len(lore_subtask_failed)}"

    # Check subtask_key format
    keys = {e.get("meta", {}).get("subtask_key") for e in lore_subtask_completed}
    assert "dim:tech" in keys
    assert "dim:schools" in keys


@pytest.mark.asyncio
async def test_characters_emits_subtask_completed_per_character():
    """characters 阶段完成时 emit 每个角色的 subtask_completed 事件（回放模式）。"""
    from schemas.character_v2 import Character, CharacterRosterEntry
    from schemas.lore_pack import LorePack
    from schemas.research_pack import IPCanon, ResearchPack
    from schemas.shared_events import RelationsPack

    agent = _build_v2_agent_with_mocks()

    char_list = [
        Character(name="Alice", personality="brave"),
        Character(name="Bob", personality="clever"),
        Character(name="Carol", personality="wise"),
    ]

    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(return_value=ResearchPack(summary="", passages=[], ip_canon=IPCanon())),
        ),
        patch("services.world_creator_agent_v2.build_lore_dimensions", AsyncMock(return_value=[])),
        patch("services.world_creator_agent_v2.build_lore_pack", AsyncMock(return_value=LorePack())),
        patch(
            "services.world_creator_agent_v2.build_character_roster",
            AsyncMock(return_value=[
                CharacterRosterEntry(name=c.name, role_tag="r", is_image_target=False)
                for c in char_list
            ]),
        ),
        patch("services.world_creator_agent_v2.build_characters_in_batches", AsyncMock(return_value=char_list)),
        patch("services.world_creator_agent_v2.build_shared_events", AsyncMock(return_value=[])),
        patch("services.world_creator_agent_v2.build_relations_pack", MagicMock(return_value=RelationsPack())),
        patch("services.world_creator_agent_v2.build_events_data", AsyncMock(return_value=[])),
        patch("services.world_creator_agent_v2.light_critic_shared_events", AsyncMock(return_value=[])),
        patch("services.world_creator_agent_v2.moderate_world_payload", AsyncMock(return_value=[])),
    ):
        events = []
        async for event in agent.create_world("desc", "", ""):
            events.append(event)

    char_subtask_events = [
        e for e in events
        if e.get("type") == "progress"
        and e.get("phase") == "characters"
        and e.get("code") == "subtask_completed"
    ]
    assert len(char_subtask_events) == 3, f"expected 3 subtask_completed for characters, got {len(char_subtask_events)}"

    keys = {e.get("meta", {}).get("subtask_key") for e in char_subtask_events}
    assert "char:Alice" in keys
    assert "char:Bob" in keys
    assert "char:Carol" in keys
