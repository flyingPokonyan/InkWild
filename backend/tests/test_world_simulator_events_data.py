"""Unit tests for WorldSimulator events_data trigger processing (Task 5.4)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from engine.state_manager import GameState
from engine.world_simulator import WorldSimulator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sim() -> WorldSimulator:
    """Return a WorldSimulator with all subsystems mocked out (no side-effects)."""
    sim = WorldSimulator(
        intent_system=MagicMock(advance=MagicMock(return_value=[])),
        info_propagation=MagicMock(propagate=MagicMock(return_value=[])),
        world_clock=MagicMock(
            advance=MagicMock(
                return_value=MagicMock(events=[], environment_changes=[])
            )
        ),
    )
    return sim


def _make_state(**kwargs) -> GameState:
    """Build a minimal GameState; kwargs override defaults."""
    defaults = dict(
        current_time="day_5_morning",
        current_location="朝堂",
    )
    defaults.update(kwargs)
    return GameState(**defaults)


def _conditional_event(
    event_id: str = "e1",
    summary: str = "测试事件",
    condition_dsl: str = "time_after('day_3')",
    probability: float = 1.0,
    world_state_changes: dict | None = None,
    spawn_clues: list | None = None,
    npc_mood_changes: dict | None = None,
    disabled: bool = False,
) -> dict:
    return {
        "id": event_id,
        "kind": "conditional",
        "summary": summary,
        "trigger": {
            "condition_dsl": condition_dsl,
            "probability": probability,
        },
        "effects": {
            "world_state_changes": world_state_changes or {},
            "spawn_clues": spawn_clues or [],
            "npc_mood_changes": npc_mood_changes or {},
        },
        "rumors": [],
        "disabled": disabled,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_events_data_conditional_trigger_fires():
    """Condition met + probability 1.0 → world_event produced, effects applied."""
    sim = _make_sim()
    state = _make_state(current_time="day_5_morning", current_location="朝堂")
    world = {
        "events_data": [
            _conditional_event(
                event_id="e1",
                summary="誉王朝堂发难",
                condition_dsl="time_after('day_3') AND location_is('朝堂')",
                probability=1.0,
                world_state_changes={"靖王处境": "危急"},
                spawn_clues=["誉王身份"],
                npc_mood_changes={"誉王": "激动"},
            )
        ]
    }
    result = sim.tick(state, world)
    updated = result.updated_state

    # WorldEvent produced
    descriptions = [e.description for e in result.world_events]
    assert any("誉王" in d for d in descriptions), f"Expected 誉王 in {descriptions}"

    # world_state updated
    assert updated.world_state.get("靖王处境") == "危急"

    # clue spawned
    clue_contents = [c["content"] for c in updated.discovered_clues]
    assert "誉王身份" in clue_contents

    # npc mood changed
    assert updated.npc_relations.get("誉王", {}).get("mood") == "激动"

    # event marked as triggered
    assert "e1" in updated.triggered_event_ids


@pytest.mark.no_db
def test_events_data_disabled_skipped():
    """disabled=True → event skipped, no trigger, no effects."""
    sim = _make_sim()
    state = _make_state(current_time="day_5_morning")
    world = {
        "events_data": [
            _conditional_event(
                event_id="e1",
                summary="S",
                world_state_changes={"key": "value"},
                disabled=True,
            )
        ]
    }
    result = sim.tick(state, world)
    updated = result.updated_state

    assert "e1" not in updated.triggered_event_ids
    assert not any("S" in e.description for e in result.world_events)
    assert updated.world_state.get("key") is None


@pytest.mark.no_db
def test_events_data_already_triggered_skipped():
    """Event already in triggered_event_ids → not re-applied."""
    sim = _make_sim()
    state = _make_state(current_time="day_5_morning", triggered_event_ids={"e1"})
    world = {
        "events_data": [
            _conditional_event(
                event_id="e1",
                world_state_changes={"x": "changed"},
            )
        ]
    }
    result = sim.tick(state, world)
    # Effects must NOT be applied again
    assert result.updated_state.world_state.get("x") is None


@pytest.mark.no_db
def test_events_data_condition_false_no_trigger():
    """Condition evaluates to False → event not triggered."""
    sim = _make_sim()
    state = _make_state(current_time="day_1_morning")  # day 1 < day 3 threshold
    world = {
        "events_data": [
            _conditional_event(
                event_id="e1",
                condition_dsl="time_after('day_3')",
                world_state_changes={"fired": True},
            )
        ]
    }
    result = sim.tick(state, world)
    assert "e1" not in result.updated_state.triggered_event_ids
    assert result.updated_state.world_state.get("fired") is None


@pytest.mark.no_db
def test_events_data_npc_intent_driven_injects_intent():
    """npc_intent_driven kind → npc_intents updated, WorldEvent produced."""
    sim = _make_sim()
    state = _make_state(current_time="day_5_morning")
    world = {
        "events_data": [
            {
                "id": "e1",
                "kind": "npc_intent_driven",
                "summary": "誉王发难",
                "trigger": {
                    "npc_name": "誉王",
                    "condition_dsl": "time_after('day_3')",
                    "intent_payload": {"goal": "弹劾靖王", "method": "联合礼部"},
                },
                "effects": {
                    "world_state_changes": {},
                    "spawn_clues": [],
                    "npc_mood_changes": {},
                },
                "rumors": [],
                "disabled": False,
            }
        ]
    }
    result = sim.tick(state, world)
    updated = result.updated_state

    assert updated.npc_intents.get("誉王") == {"goal": "弹劾靖王", "method": "联合礼部"}
    assert "e1" in updated.triggered_event_ids
    descriptions = [e.description for e in result.world_events]
    assert any("誉王" in d for d in descriptions)


@pytest.mark.no_db
def test_events_data_invalid_dsl_runtime_skipped():
    """Bogus condition_dsl → parse error caught, event skipped, no exception raised."""
    sim = _make_sim()
    state = _make_state()
    world = {
        "events_data": [
            _conditional_event(
                event_id="e1",
                condition_dsl="@@@bogus@@@",
            )
        ]
    }
    # Must not raise
    result = sim.tick(state, world)
    assert "e1" not in result.updated_state.triggered_event_ids


@pytest.mark.no_db
def test_events_data_probability_zero_no_trigger():
    """probability=0.0 → random check always fails, event never triggered."""
    sim = _make_sim()
    state = _make_state(current_time="day_5_morning")
    world = {
        "events_data": [
            _conditional_event(
                event_id="e1",
                condition_dsl="time_after('day_3')",
                probability=0.0,
            )
        ]
    }
    # Run many times to be certain
    for _ in range(20):
        result = sim.tick(state, world)
        # state is deep-copied each tick, so triggered_event_ids stays empty
        assert "e1" not in result.updated_state.triggered_event_ids


@pytest.mark.no_db
def test_events_data_no_field_compatibility():
    """world_config without events_data → no error (old-world compatibility)."""
    sim = _make_sim()
    state = _make_state()
    world = {}  # no events_data key
    result = sim.tick(state, world)
    assert result is not None
    assert result.updated_state is not None


@pytest.mark.no_db
def test_events_data_spawn_multiple_clues():
    """Multiple spawn_clues entries → all added to discovered_clues."""
    sim = _make_sim()
    state = _make_state(current_time="day_5_morning")
    world = {
        "events_data": [
            _conditional_event(
                event_id="e1",
                spawn_clues=["线索A", "线索B", "线索C"],
            )
        ]
    }
    result = sim.tick(state, world)
    contents = [c["content"] for c in result.updated_state.discovered_clues]
    assert "线索A" in contents
    assert "线索B" in contents
    assert "线索C" in contents


@pytest.mark.no_db
def test_events_data_no_duplicate_on_second_tick():
    """Event triggered on first tick; second tick uses the updated state → not re-triggered."""
    sim = _make_sim()
    state = _make_state(current_time="day_5_morning")
    world = {
        "events_data": [
            _conditional_event(
                event_id="e1",
                world_state_changes={"靖王处境": "危急"},
                spawn_clues=["线索X"],
            )
        ]
    }
    result1 = sim.tick(state, world)
    assert "e1" in result1.updated_state.triggered_event_ids

    # Second tick starts from updated state (where e1 is already triggered)
    result2 = sim.tick(result1.updated_state, world)
    assert "e1" in result2.updated_state.triggered_event_ids
    # discovered_clues should still have only one entry for 线索X
    clue_contents = [c["content"] for c in result2.updated_state.discovered_clues]
    assert clue_contents.count("线索X") == 1


@pytest.mark.no_db
def test_events_data_probability_clamped_negative():
    """probability < 0 → clamped to 0.0, never triggers."""
    sim = _make_sim()
    state = _make_state(current_time="day_5_morning")
    world = {
        "events_data": [
            _conditional_event(
                event_id="e1",
                condition_dsl="time_after('day_3')",
                probability=-5.0,
            )
        ]
    }
    result = sim.tick(state, world)
    assert "e1" not in result.updated_state.triggered_event_ids


@pytest.mark.no_db
def test_events_data_probability_clamped_above_one():
    """probability > 1 → clamped to 1.0, always triggers."""
    sim = _make_sim()
    state = _make_state(current_time="day_5_morning")
    world = {
        "events_data": [
            _conditional_event(
                event_id="e1",
                condition_dsl="time_after('day_3')",
                probability=99.0,
            )
        ]
    }
    result = sim.tick(state, world)
    assert "e1" in result.updated_state.triggered_event_ids
