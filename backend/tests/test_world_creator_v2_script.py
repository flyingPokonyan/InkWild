"""Tests for WorldCreatorAgentV2.create_script — v2 8-stage script pipeline.

Verifies:
- All 8 stages emit started + completed progress events (research_pack, script_base,
  events, endings, playable, critic, script_visual_brief, script_images)
- Script v2 does NOT regenerate world fields (characters / lore_pack / shared_events)
- Result payload contains required keys (events, events_data, endings, playable,
  research_pack, quality_warnings)
- Playable selection is derived from world_data without LLM call
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.world_creator_agent_v2 import WorldCreatorAgentV2


@pytest.fixture(autouse=True)
def _lower_fail_fast_thresholds(monkeypatch):
    """Script tests use mock LLMs that may return 0 endings. The 2026-05-24
    endings fail-fast gate would abort before downstream stages emit; this
    fixture disables the gate so shape assertions still run."""
    monkeypatch.setattr("services.world_creator_agent_v2._MIN_CHARACTERS", 0)
    monkeypatch.setattr("services.world_creator_agent_v2._MIN_EVENTS_DATA", 0)
    monkeypatch.setattr("services.world_creator_agent_v2._MIN_SCRIPT_ENDINGS", 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_v2_agent_with_mocks() -> WorldCreatorAgentV2:
    """Construct v2 agent with all external dependencies mocked."""
    fake_llm = MagicMock()

    async def _fake_stream(*, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": "{}"}

    fake_llm.stream_with_tools = _fake_stream

    fake_broker = MagicMock()
    fake_broker.collect_passages = AsyncMock(return_value=[])
    fake_broker.summarize_passages = AsyncMock(return_value="")

    return WorldCreatorAgentV2(
        llm=fake_llm,
        image_gen=MagicMock(),
        broker=fake_broker,
    )


def _world_data_minimal() -> dict:
    """Minimal world_data payload covering all fields create_script reads."""
    return {
        "name": "Test World",
        "description": "A test world description.",
        "base_setting": "The world base setting.",
        "genre": "mystery",
        "era": "modern",
        "world_characters": [
            {
                "id": "alice-id",
                "name": "Alice",
                "personality": "Brave and curious",
                "is_image_target": True,
                "playable": True,
                "role_tag": "主角",
                "secret": "Has a hidden past",
                "knowledge": ["clue1"],
                "schedule": {},
                "initial_location": "library",
                "faction": "",
            },
            {
                "id": "bob-id",
                "name": "Bob",
                "personality": "Suspicious",
                "is_image_target": False,
                "playable": False,
                "role_tag": "嫌疑人",
                "secret": "",
                "knowledge": [],
                "schedule": {},
                "initial_location": "study",
                "faction": "",
            },
        ],
        "locations": [
            {"name": "library", "description": "A dusty old library"},
            {"name": "study", "description": "A private study"},
        ],
        "lore_pack": {"dimensions": []},
        "shared_events": [],
        "research_pack": {
            "summary": "",
            "passages": [],
            "ip_canon": {
                "title_guesses": [],
                "canonical_names": ["Alice", "Bob"],
                "canonical_places": ["library"],
                "iconic_objects": [],
                "lingo": [],
                "notable_events": [],
            },
        },
    }


def _common_patches():
    """Return patch context managers for external calls used by create_script."""
    from schemas.research_pack import IPCanon, ResearchPack

    return [
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(
                return_value=ResearchPack(
                    summary="", passages=[], ip_canon=IPCanon()
                )
            ),
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
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_script_emits_all_stages():
    """All 8 stages emit a 'started' progress event."""
    agent = _build_v2_agent_with_mocks()
    patches = _common_patches()
    for p in patches:
        p.__enter__()

    try:
        events = []
        async for event in agent.create_script(_world_data_minimal(), outline="A murder mystery outline"):
            events.append(event)
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)

    # Events are flat: {"type": "progress", "phase": ..., "code": ...}
    started_phases = {
        e["phase"]
        for e in events
        if e.get("type") == "progress" and e.get("code") == "started"
    }
    expected = {
        "research_pack", "script_base", "events", "endings",
        "playable", "critic", "script_visual_brief", "script_images",
    }
    assert expected.issubset(started_phases), (
        f"Missing started phases: {expected - started_phases}"
    )


@pytest.mark.asyncio
async def test_create_script_emits_playable_character_ids_resolved_to_playable_only():
    """V2 result must carry playable_character_ids as world-character UUIDs,
    constrained to actually-playable characters (Bob is not playable → excluded)."""
    agent = _build_v2_agent_with_mocks()
    patches = _common_patches()
    for p in patches:
        p.__enter__()
    try:
        result = None
        async for event in agent.create_script(_world_data_minimal(), outline="x"):
            if event.get("type") == "result":
                result = event
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)

    assert result is not None
    assert result["playable_character_ids"] == ["alice-id"]


@pytest.mark.asyncio
async def test_create_script_does_not_regenerate_world_fields():
    """Script v2 must not call world-generation builders for characters / lore / shared_events."""
    agent = _build_v2_agent_with_mocks()

    from schemas.research_pack import IPCanon, ResearchPack

    with (
        patch("services.world_creator_agent_v2.build_character_roster") as roster_mock,
        patch("services.world_creator_agent_v2.build_characters_in_batches") as char_mock,
        patch("services.world_creator_agent_v2.build_lore_dimensions") as lore_dim_mock,
        patch("services.world_creator_agent_v2.build_lore_pack") as lore_mock,
        patch("services.world_creator_agent_v2.build_shared_events") as se_mock,
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(
                return_value=ResearchPack(
                    summary="", passages=[], ip_canon=IPCanon()
                )
            ),
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
        async for event in agent.create_script(_world_data_minimal(), outline="x"):
            events.append(event)

    # None of the world-building functions should have been invoked
    roster_mock.assert_not_called()
    char_mock.assert_not_called()
    lore_dim_mock.assert_not_called()
    lore_mock.assert_not_called()
    se_mock.assert_not_called()


@pytest.mark.asyncio
async def test_create_script_emits_result_with_required_keys():
    """Result event payload contains all required keys."""
    agent = _build_v2_agent_with_mocks()
    patches = _common_patches()
    for p in patches:
        p.__enter__()

    try:
        events = []
        async for event in agent.create_script(_world_data_minimal(), outline="x"):
            events.append(event)
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)

    result_events = [e for e in events if e.get("type") == "result"]
    assert len(result_events) == 1, "Expected exactly one result event"

    # result_event spreads data directly: {"type": "result", ...data_fields}
    payload = result_events[0]
    required_keys = {"events", "events_data", "endings", "playable", "research_pack", "quality_warnings"}
    for key in required_keys:
        assert key in payload, f"Result payload missing key: {key}"


@pytest.mark.asyncio
async def test_create_script_playable_from_world_data():
    """Playable characters are selected from world_data without an LLM call."""
    agent = _build_v2_agent_with_mocks()
    patches = _common_patches()
    for p in patches:
        p.__enter__()

    try:
        events = []
        async for event in agent.create_script(_world_data_minimal(), outline="x"):
            events.append(event)
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)

    result = next((e for e in events if e.get("type") == "result"), None)
    assert result is not None

    # result_event spreads data directly: {"type": "result", ...data_fields}
    playable = result["playable"]
    names = {p["name"] for p in playable}

    # Alice: is_image_target=True + playable=True + role_tag=主角 → must be selected
    assert "Alice" in names, f"Expected Alice in playable, got: {names}"
    # Bob: is_image_target=False + playable=False + role_tag=嫌疑人 → not selected
    assert "Bob" not in names, f"Bob should not be in playable, got: {names}"


@pytest.mark.asyncio
async def test_create_script_emits_done_event():
    """Pipeline must emit a 'done' event as the final event."""
    agent = _build_v2_agent_with_mocks()
    patches = _common_patches()
    for p in patches:
        p.__enter__()

    try:
        events = []
        async for event in agent.create_script(_world_data_minimal(), outline="x"):
            events.append(event)
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)

    assert events, "No events emitted"
    assert events[-1].get("type") == "done", f"Last event should be 'done', got {events[-1].get('type')}"


@pytest.mark.asyncio
async def test_create_script_playable_fallback_when_none_qualify():
    """When no character qualifies, fall back to first 3 characters."""
    agent = _build_v2_agent_with_mocks()
    patches = _common_patches()
    for p in patches:
        p.__enter__()

    world_data = _world_data_minimal()
    # Make neither character qualify as is_image_target / playable / 主角
    for c in world_data["world_characters"]:
        c["is_image_target"] = False
        c["playable"] = False
        c["role_tag"] = "NPC"

    try:
        events = []
        async for event in agent.create_script(world_data, outline="x"):
            events.append(event)
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)

    result = next((e for e in events if e.get("type") == "result"), None)
    assert result is not None
    # result_event spreads data directly: {"type": "result", ...data_fields}
    playable = result["playable"]
    # Fallback: should return up to first 3 characters
    assert len(playable) > 0, "Fallback should return at least one playable character"
    assert len(playable) <= 3


@pytest.mark.asyncio
async def test_select_script_playable_v2_direct():
    """Unit test for _select_script_playable_v2 logic."""
    agent = _build_v2_agent_with_mocks()

    chars = [
        {"name": "Hero", "role_tag": "主角", "personality": "brave", "is_image_target": False, "playable": False},
        {"name": "Villain", "role_tag": "反派", "personality": "evil", "is_image_target": False, "playable": False},
        {"name": "Target", "role_tag": "路人", "personality": "calm", "is_image_target": True, "playable": False},
        {"name": "Playable", "role_tag": "副角", "personality": "smart", "is_image_target": False, "playable": True},
    ]

    result = agent._select_script_playable_v2(chars)
    names = {r["name"] for r in result}

    assert "Hero" in names, "主角 role_tag should be included"
    assert "Target" in names, "is_image_target=True should be included"
    assert "Playable" in names, "playable=True should be included (mapped to is_image_target)"
    assert "Villain" not in names, "反派 with no qualifiers should NOT be included"


def _build_v2_agent_with_llm_text(text: str) -> WorldCreatorAgentV2:
    """v2 agent whose LLM streams a fixed text payload (for curated playable test)."""
    fake_llm = MagicMock()

    async def _fake_stream(*, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": text}

    fake_llm.stream_with_tools = _fake_stream
    fake_broker = MagicMock()
    fake_broker.collect_passages = AsyncMock(return_value=[])
    fake_broker.summarize_passages = AsyncMock(return_value="")
    return WorldCreatorAgentV2(llm=fake_llm, image_gen=MagicMock(), broker=fake_broker)


_CURATE_CHARS = [
    {"name": "Alice", "role_tag": "主角", "personality": "brave", "playable": True},
    {"name": "Bob", "role_tag": "副角", "personality": "calm", "playable": True},
    {"name": "Carol", "role_tag": "副角", "personality": "smart", "playable": True},
    {"name": "Dave", "role_tag": "副角", "personality": "quiet", "playable": True},
]


@pytest.mark.asyncio
async def test_select_script_playable_curated_llm_subset():
    """LLM picks a curated subset of the world-playable characters (not all)."""
    import json

    agent = _build_v2_agent_with_llm_text(
        json.dumps({"playable_characters": [{"name": "Alice"}, {"name": "Carol"}]})
    )
    result = await agent._select_script_playable_curated(
        _CURATE_CHARS, {"name": "S", "description": "d"}
    )
    assert [r["name"] for r in result] == ["Alice", "Carol"]


@pytest.mark.asyncio
async def test_select_script_playable_curated_fallback_on_empty():
    """LLM returns nothing usable → fall back to all world-playable (never crashes/empties)."""
    agent = _build_v2_agent_with_llm_text("{}")
    result = await agent._select_script_playable_curated(
        _CURATE_CHARS, {"name": "S", "description": "d"}
    )
    assert {r["name"] for r in result} == {"Alice", "Bob", "Carol", "Dave"}


@pytest.mark.asyncio
async def test_select_script_playable_curated_ignores_hallucinated_names():
    """Names not in the candidate list are dropped (no NPC/invented POVs leak in)."""
    import json

    agent = _build_v2_agent_with_llm_text(
        json.dumps({"playable_characters": [{"name": "Alice"}, {"name": "Ghost"}]})
    )
    result = await agent._select_script_playable_curated(
        _CURATE_CHARS, {"name": "S", "description": "d"}
    )
    assert [r["name"] for r in result] == ["Alice"]


# ---------------------------------------------------------------------------
# Silent-failure → SSE warning regression tests (2026-05-20)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_script_events_failure_emits_warning():
    """Regression: build_events_data raising used to be swallowed with only a
    structlog warning; admin saw `events:completed event_count=0` and never
    knew the stage failed. Now an SSE warning with code=script_events_failed
    must appear before the completed event.
    """
    from schemas.research_pack import IPCanon, ResearchPack

    agent = _build_v2_agent_with_mocks()
    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(
                return_value=ResearchPack(summary="", passages=[], ip_canon=IPCanon())
            ),
        ),
        patch(
            "services.world_creator_agent_v2.build_events_data",
            AsyncMock(side_effect=RuntimeError("boom")),
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
        events = [
            ev async for ev in agent.create_script(
                _world_data_minimal(), outline="A test outline"
            )
        ]

    warnings = [
        e for e in events
        if e.get("type") == "warning" and e.get("code") == "script_events_failed"
    ]
    assert warnings, "must emit a script_events_failed warning when build_events_data raises"
    assert warnings[0].get("phase") == "events"
    assert warnings[0]["meta"].get("error_type") == "RuntimeError"


@pytest.mark.asyncio
async def test_script_endings_failure_emits_warning():
    """Same regression on the endings inner helper: when the endings LLM call
    fails through with_transient_retry, the outer create_script must emit a
    warning with code=endings_generation_failed (driven by self._stage_errors).
    """
    from schemas.research_pack import IPCanon, ResearchPack

    agent = _build_v2_agent_with_mocks()

    async def _stream_raises(*, messages, tools, system, max_tokens):
        # Streaming LLM raises for the endings call (and everything else, but
        # the test only asserts the endings path).
        raise RuntimeError("endings boom")
        yield  # pragma: no cover - keep this an async generator

    agent.llm.stream_with_tools = _stream_raises

    with (
        patch(
            "services.world_creator_agent_v2.build_research_pack",
            AsyncMock(
                return_value=ResearchPack(summary="", passages=[], ip_canon=IPCanon())
            ),
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
        events = [
            ev async for ev in agent.create_script(
                _world_data_minimal(), outline="A test outline"
            )
        ]

    warnings = [
        e for e in events
        if e.get("type") == "warning" and e.get("code") == "endings_generation_failed"
    ]
    assert warnings, "must emit endings_generation_failed warning when endings LLM raises"
    assert warnings[0].get("phase") == "endings"


def test_stage_failure_warning_shape():
    """Unit test for the _stage_failure_warning helper."""
    from services.world_creator_agent_v2 import _stage_failure_warning

    exc = ValueError("something broke" + "x" * 600)  # long error to test trunc
    ev = _stage_failure_warning("events", "script_events_failed", exc, "test message")

    assert ev["type"] == "warning"
    assert ev["phase"] == "events"
    assert ev["code"] == "script_events_failed"
    assert "test message" in ev["message"]
    assert "ValueError" in ev["message"]
    assert ev["meta"]["error_type"] == "ValueError"
    assert len(ev["meta"]["error"]) <= 500  # truncated
