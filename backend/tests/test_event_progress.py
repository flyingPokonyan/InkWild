"""Runtime v2 — event progress calculator."""

from __future__ import annotations

import pytest

from engine.event_progress import (
    build_director_event_payload,
    compute_event_progress,
)
from engine.state_manager import GameState

pytestmark = pytest.mark.no_db


def _state(**overrides) -> GameState:
    base = GameState(
        current_time="day_2·上午",
        current_location="大理寺",
        world_state={"key_evidence_found": 1},
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_no_events_returns_empty():
    out = compute_event_progress(None, _state())
    assert out == []


def test_fired_event_progress_is_one():
    events_data = [
        {
            "id": "evt_1",
            "name": "案件揭开",
            "trigger": {"condition_dsl": "world_state.key_evidence_found >= 1"},
        }
    ]
    state = _state(triggered_event_ids={"evt_1"})
    out = compute_event_progress(events_data, state)
    assert len(out) == 1
    assert out[0].fired is True
    assert out[0].progress == 1.0


def test_simple_leaf_satisfied():
    events_data = [
        {
            "id": "evt_1",
            "name": "X",
            "trigger": {"condition_dsl": "world_state.key_evidence_found >= 1"},
        }
    ]
    out = compute_event_progress(events_data, _state())
    assert out[0].progress == 1.0
    assert out[0].total_leaves == 1


def test_simple_leaf_unsatisfied():
    events_data = [
        {
            "id": "evt_1",
            "name": "X",
            "trigger": {"condition_dsl": "world_state.key_evidence_found >= 5"},
        }
    ]
    out = compute_event_progress(events_data, _state())
    assert out[0].progress == 0.0


def test_and_partial_progress():
    # 1 of 2 leaves satisfied → 0.5
    events_data = [
        {
            "id": "evt_1",
            "name": "X",
            "trigger": {
                "condition_dsl": "world_state.key_evidence_found >= 1 AND location_is('禁地')"
            },
        }
    ]
    out = compute_event_progress(events_data, _state())
    assert out[0].progress == 0.5
    assert out[0].satisfied_leaves == 1
    assert out[0].total_leaves == 2


def test_or_partial_progress():
    # 1 of 2 leaves under OR — progress reflects raw leaf count, not OR logic
    events_data = [
        {
            "id": "evt_1",
            "name": "X",
            "trigger": {
                "condition_dsl": "world_state.key_evidence_found >= 1 OR location_is('禁地')"
            },
        }
    ]
    out = compute_event_progress(events_data, _state())
    # 1/2 satisfied
    assert out[0].progress == 0.5


def test_not_inverts_leaf():
    # NOT(satisfied) → unsatisfied leaf
    events_data = [
        {
            "id": "evt_1",
            "name": "X",
            "trigger": {"condition_dsl": "NOT (world_state.key_evidence_found >= 1)"},
        }
    ]
    out = compute_event_progress(events_data, _state())
    assert out[0].progress == 0.0


def test_disabled_event_skipped():
    events_data = [
        {
            "id": "evt_1",
            "disabled": True,
            "name": "X",
            "trigger": {"condition_dsl": "world_state.key_evidence_found >= 1"},
        }
    ]
    out = compute_event_progress(events_data, _state())
    assert out == []


def test_missing_dsl_gets_zero_progress():
    events_data = [{"id": "evt_1", "name": "X", "trigger": {}}]
    out = compute_event_progress(events_data, _state())
    assert out[0].progress == 0.0
    assert out[0].total_leaves == 1


def test_unparseable_dsl_handled():
    events_data = [
        {
            "id": "evt_1",
            "name": "X",
            "trigger": {"condition_dsl": "this is not valid"},
        }
    ]
    out = compute_event_progress(events_data, _state())
    assert out[0].progress == 0.0


def test_director_payload_sorts_active_descending():
    events_data = [
        {
            "id": "evt_low",
            "name": "L",
            "trigger": {"condition_dsl": "world_state.key_evidence_found >= 5"},
        },
        {
            "id": "evt_high",
            "name": "H",
            "trigger": {"condition_dsl": "world_state.key_evidence_found >= 1"},
        },
    ]
    payload = build_director_event_payload(events_data, _state())
    assert payload["fired"] == []
    assert payload["active"][0]["id"] == "evt_high"
    assert payload["active"][0]["progress"] == 1.0


def test_director_payload_fired_segregated():
    events_data = [
        {
            "id": "evt_1",
            "name": "X",
            "trigger": {"condition_dsl": "world_state.key_evidence_found >= 1"},
        }
    ]
    state = _state(triggered_event_ids={"evt_1"})
    payload = build_director_event_payload(events_data, state)
    assert payload["fired"] == ["evt_1"]
    assert payload["active"] == []
