"""Tests for WorldCreatorAgentV2 entry point (Task 1.9).

M1 scope: only research_pack phase runs; other phases emit warning(not_yet_implemented).

Note on event format: events use {"type": "<name>", ...} (matching generation_feedback helpers
and _record_event in generation_task_service). This is NOT {"event": ...}.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.world_creator_agent_v2 import WorldCreatorAgentV2


@pytest.fixture(autouse=True)
def _lower_fail_fast_thresholds(monkeypatch):
    """Entry tests use 0-1 char / 0 event mocks that pre-date the 2026-05-24
    fail-fast gates. Lower thresholds here so shape assertions still run;
    gate semantics are covered in tests/test_pipeline_fail_fast.py.
    """
    monkeypatch.setattr("services.world_creator_agent_v2._MIN_CHARACTERS", 0)
    monkeypatch.setattr("services.world_creator_agent_v2._MIN_EVENTS_DATA", 0)
    monkeypatch.setattr("services.world_creator_agent_v2._MIN_SCRIPT_ENDINGS", 0)


def _build_v2_agent():
    """Construct a v2 agent with all dependencies mocked."""
    fake_llm = MagicMock()

    async def fake_stream(*, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": '{"canonical_names":["A"]}'}

    fake_llm.stream_with_tools = fake_stream

    fake_broker = MagicMock()
    fake_broker.collect_passages = AsyncMock(return_value=[])
    fake_broker.summarize_passages = AsyncMock(return_value="摘要")

    # image_gen=None uses the fast placeholder path in _run_images — avoids needing
    # OSS credentials or real Seedream access in unit tests.
    return WorldCreatorAgentV2(
        llm=fake_llm,
        image_gen=None,
        broker=fake_broker,
    )


@pytest.mark.asyncio
async def test_v2_create_world_emits_research_pack_lifecycle():
    """M1: v2 should emit research_pack started + completed events."""
    agent = _build_v2_agent()
    events = []
    async for event in agent.create_world("一段描述", "悬疑", "民国"):
        events.append(event)

    # At least one progress event with phase=research_pack
    phases = [e["phase"] for e in events if e.get("type") == "progress"]
    assert "research_pack" in phases

    research_codes = [
        e["code"]
        for e in events
        if e.get("type") == "progress" and e.get("phase") == "research_pack"
    ]
    assert "started" in research_codes
    assert "completed" in research_codes


@pytest.mark.asyncio
async def test_v2_create_world_emits_result_with_research_pack():
    agent = _build_v2_agent()
    events = []
    async for event in agent.create_world("desc", "", ""):
        events.append(event)

    result_events = [e for e in events if e.get("type") == "result"]
    assert len(result_events) == 1
    payload = result_events[0]
    assert "research_pack" in payload
    assert "passages" in payload["research_pack"]
    assert "ip_canon" in payload["research_pack"]


@pytest.mark.asyncio
async def test_v2_create_world_ends_with_done():
    agent = _build_v2_agent()
    events = []
    async for event in agent.create_world("desc", "", ""):
        events.append(event)

    assert events[-1].get("type") == "done"


@pytest.mark.asyncio
async def test_v2_create_world_emits_all_major_phase_events():
    """M2+: v2 should emit progress events for all 12+ stages (no longer placeholder warnings)."""
    agent = _build_v2_agent()
    events = []
    async for event in agent.create_world("desc", "", ""):
        events.append(event)

    progress_phases = [e["phase"] for e in events if e.get("type") == "progress"]
    # All major phases should be represented
    for phase in ("research_pack", "world_base", "lore_pack", "characters",
                  "shared_events", "events_data", "playable", "critic", "validating"):
        assert phase in progress_phases, f"expected phase {phase!r} in progress events"


@pytest.mark.asyncio
async def test_launch_world_generation_uses_v2_when_flag_enabled(
    monkeypatch, generation_task_service, db
):
    """When settings.world_creator_v2_enabled=True, v2 path is taken."""
    import config
    from models.user import User
    monkeypatch.setattr(config.settings, "world_creator_v2_enabled", True)

    user = User(nickname="v2_tester", is_admin=False)
    db.add(user)
    await db.commit()

    draft_id, task_id = await generation_task_service.start_world_generation(
        description="测试", genre="", era="", user_id=str(user.id),
    )

    v2_called = []

    async def fake_create_world(self, description, genre="", era=""):
        v2_called.append(description)
        yield {
            "type": "progress",
            "phase": "research_pack",
            "code": "started",
            "message": "",
            "meta": {},
        }
        yield {"type": "result", "research_pack": {"summary": "", "passages": [], "ip_canon": {}}}
        yield {"type": "done"}

    monkeypatch.setattr(
        "services.world_creator_agent_v2.WorldCreatorAgentV2.create_world",
        fake_create_world,
    )

    # We also need world_creator_factory to return something non-None
    # so v2 can steal its attributes. Use a minimal stub.
    stub_agent = MagicMock()
    stub_agent.llm = MagicMock()
    stub_agent.image_gen = None
    stub_agent.research_broker = MagicMock()

    monkeypatch.setattr(generation_task_service, "world_creator_factory", lambda: stub_agent)

    await generation_task_service._run_world_generation(task_id)

    assert v2_called == ["测试"], f"v2 agent should have been called, got: {v2_called}"


@pytest.mark.asyncio
async def test_launch_world_generation_uses_v1_when_flag_disabled(
    monkeypatch, generation_task_service, db
):
    """When settings.world_creator_v2_enabled=False, v1 path is taken (agent passed through as-is)."""
    import config
    from models.user import User
    monkeypatch.setattr(config.settings, "world_creator_v2_enabled", False)

    user = User(nickname="v1_tester", is_admin=False)
    db.add(user)
    await db.commit()

    draft_id, task_id = await generation_task_service.start_world_generation(
        description="测试 v1", genre="", era="", user_id=str(user.id),
    )

    v1_called = []

    # For v1, the agent returned by the factory is used directly.
    # We stub the factory to return an object whose create_world is an async generator.
    async def fake_create_world(description, genre="", era=""):
        v1_called.append(description)
        yield {"type": "result"}
        yield {"type": "done"}

    stub_v1_agent = MagicMock()
    stub_v1_agent.llm = MagicMock()
    stub_v1_agent.image_gen = None
    stub_v1_agent.research_broker = MagicMock()
    stub_v1_agent.create_world = fake_create_world

    monkeypatch.setattr(generation_task_service, "world_creator_factory", lambda: stub_v1_agent)

    await generation_task_service._run_world_generation(task_id)

    assert v1_called == ["测试 v1"], f"v1 agent should have been called, got: {v1_called}"


# ---------------------------------------------------------------------------
# Task 6: enriched completed event meta (sample / clue_count / etc.)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_events_completed_carries_sample_and_event_count(monkeypatch):
    """shared_events.completed should include event_count + sample (event titles)."""
    from schemas.shared_events import SharedEvent
    from schemas.research_pack import ResearchPack
    from services import world_creator_agent_v2 as v2_mod

    fixed_events = [
        SharedEvent(id="se1", title="科举舞弊案", summary="x"),
        SharedEvent(id="se2", title="安禄山入长安", summary="y"),
        SharedEvent(id="se3", title="月夜诗会", summary="z"),
    ]

    async def fake_build(*args, **kwargs):
        return fixed_events

    monkeypatch.setattr(v2_mod, "build_shared_events", fake_build)

    agent = _build_v2_agent()
    research_pack = ResearchPack(summary="", passages=[])

    events = []
    async for ev in agent._run_shared_events("desc", research_pack.ip_canon, [], research_pack):
        events.append(ev)

    completed = next(
        e for e in events if e.get("phase") == "shared_events" and e.get("code") == "completed"
    )
    assert completed["meta"]["event_count"] == 3
    assert completed["meta"]["sample"] == ["科举舞弊案", "安禄山入长安"]


@pytest.mark.asyncio
async def test_events_data_completed_includes_clue_count(monkeypatch):
    """events_data.completed should include clue_count = total spawn_clues across events."""
    from schemas.events_data import EventDataEntry, EventEffects
    from schemas.shared_events import SharedEvent
    from schemas.lore_pack import LorePack
    from schemas.research_pack import IPCanon
    from services import world_creator_agent_v2 as v2_mod

    fixed = [
        EventDataEntry(
            id="ev1",
            kind="conditional",
            summary="朱雀街刺杀案的发生",
            trigger={"condition_dsl": ""},
            effects=EventEffects(spawn_clues=["c1", "c2", "c3"]),
        ),
        EventDataEntry(
            id="ev2",
            kind="conditional",
            summary="月夜会客厅的密谈",
            trigger={"condition_dsl": ""},
            effects=EventEffects(spawn_clues=["c4"]),
        ),
    ]

    async def fake_build(*args, **kwargs):
        return fixed

    monkeypatch.setattr(v2_mod, "build_events_data", fake_build)

    agent = _build_v2_agent()
    completed = None
    async for ev in agent._run_events_data(
        "desc", IPCanon(), [], [], [], LorePack()
    ):
        if ev.get("phase") == "events_data" and ev.get("code") == "completed":
            completed = ev

    assert completed is not None
    assert completed["meta"]["event_count"] == 2
    assert completed["meta"]["clue_count"] == 4
    assert isinstance(completed["meta"].get("sample"), list)
    assert len(completed["meta"]["sample"]) <= 2


@pytest.mark.asyncio
async def test_lore_pack_subtask_completed_includes_dim_label(monkeypatch):
    """lore_pack subtask_completed should carry dim_label (Chinese name)."""
    from schemas.lore_pack import (
        LoreContentBlock,
        LoreDimension,
        LoreDimensionContent,
        LorePack,
    )
    from schemas.research_pack import IPCanon
    from services import world_creator_agent_v2 as v2_mod

    async def fake_build(*args, **kwargs):
        return LorePack(
            dimensions=[
                LoreDimensionContent(
                    key="religion",
                    name="宗教信仰",
                    content_blocks=[LoreContentBlock(heading="h", body="b")],
                ),
                LoreDimensionContent(
                    key="economy",
                    name="经济结构",
                    content_blocks=[LoreContentBlock(heading="h", body="b")],
                ),
            ]
        )

    monkeypatch.setattr(v2_mod, "build_lore_pack", fake_build)

    agent = _build_v2_agent()
    dims_in = [
        LoreDimension(key="religion", name="宗教信仰", why_relevant=""),
        LoreDimension(key="economy", name="经济结构", why_relevant=""),
    ]

    subtasks = []
    async for ev in agent._run_lore_pack("desc", IPCanon(), dims_in, MagicMock()):
        if ev.get("phase") == "lore_pack" and ev.get("code") == "subtask_completed":
            subtasks.append(ev)

    assert len(subtasks) == 2
    labels = [e["meta"]["payload_summary"].get("dim_label") for e in subtasks]
    assert "宗教信仰" in labels
    assert "经济结构" in labels


# ---------------------------------------------------------------------------
# Task 7: _run_with_pulse helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_with_pulse_yields_periodic_pulses_during_long_work():
    """While work runs, _run_with_pulse should emit pulse events at the configured interval,
    then yield the result tuple. The final yield is ('result', value)."""
    import asyncio as _asyncio

    agent = WorldCreatorAgentV2(llm=None, image_gen=None, broker=None)

    async def slow_work():
        await _asyncio.sleep(0.35)
        return "done"

    pulses = []
    result = None
    async for item in agent._run_with_pulse("shared_events", slow_work(), interval=0.1):
        if isinstance(item, tuple) and item[0] == "result":
            result = item[1]
        elif isinstance(item, dict):
            assert item.get("phase") == "shared_events"
            assert item.get("code") == "pulse"
            pulses.append(item)

    assert result == "done"
    assert len(pulses) >= 2, f"expected at least 2 pulses, got {len(pulses)}"


@pytest.mark.asyncio
async def test_run_with_pulse_propagates_exception():
    import asyncio as _asyncio
    agent = WorldCreatorAgentV2(llm=None, image_gen=None, broker=None)

    async def failing_work():
        await _asyncio.sleep(0.05)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        async for _item in agent._run_with_pulse("shared_events", failing_work(), interval=0.5):
            pass


@pytest.mark.asyncio
async def test_run_with_pulse_returns_immediately_for_fast_work():
    agent = WorldCreatorAgentV2(llm=None, image_gen=None, broker=None)

    async def fast_work():
        return 42

    pulses = []
    result = None
    async for item in agent._run_with_pulse("shared_events", fast_work(), interval=1.0):
        if isinstance(item, tuple) and item[0] == "result":
            result = item[1]
        else:
            pulses.append(item)

    assert result == 42
    assert len(pulses) == 0
