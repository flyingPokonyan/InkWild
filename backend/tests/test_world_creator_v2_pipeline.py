"""Integration tests for WorldCreatorAgentV2 complete 12-stage pipeline.

All builders are mocked — these tests verify pipeline structure, event ordering,
concurrency, record_intermediate calls, and result payload shape.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    from schemas.character_v2 import Character
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

import contextlib


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
