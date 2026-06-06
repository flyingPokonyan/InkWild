"""Phase 5 tests: publish-boundary schema validation."""
import pytest
from services.generation_schema import (
    SchemaValidationError,
    validate_script_payload,
    validate_world_payload,
)


def _good_ending(suffix: str = "") -> dict:
    return {
        "ending_type": "good",
        "title": f"标题{suffix}",
        "description": "玩家走向真相的完整描述" * 5,
        "soft_conditions": "玩家在 day_5 之前发现关键线索",
        "priority": 1,
        "quality": "best",
    }


def _good_event(idx: str = "evt_001") -> dict:
    return {
        "id": idx,
        "kind": "conditional",
        "summary": "test event",
        "trigger": {"condition_dsl": "time_after('day_3')", "probability": 0.8},
        "effects": {"world_state_changes": {}, "spawn_clues": [], "npc_mood_changes": {}},
        "rumors": [],
    }


def test_valid_script_passes():
    payload = {
        "name": "test",
        "script_setting": "...",
        "script_type": "mystery",
        "events_data": [_good_event("evt_1"), _good_event("evt_2"), _good_event("evt_3")],
        "endings_data": [_good_ending("A"), _good_ending("B")],
    }
    validate_script_payload(payload)


def test_script_missing_required_ending_field_raises():
    payload = {
        "name": "test",
        "script_setting": "...",
        "script_type": "mystery",
        "events_data": [_good_event("a"), _good_event("b"), _good_event("c")],
        "endings_data": [
            {
                "title": "t",
                "description": "d" * 30,
                "quality": "best",
            },
            _good_ending("B"),
        ],
    }
    with pytest.raises(SchemaValidationError) as exc:
        validate_script_payload(payload)
    assert "ending_type" in str(exc.value)


def test_script_with_disabled_event_raises():
    """A disabled event in published content means generator silently dropped logic."""
    payload = {
        "name": "test",
        "script_setting": "...",
        "script_type": "mystery",
        "events_data": [
            {
                "id": "evt_001",
                "kind": "conditional",
                "summary": "...",
                "trigger": {"condition_dsl": "bogus"},
                "effects": {},
                "rumors": [],
                "disabled": True,
                "disabled_reason": "dsl_parse_error: ...",
            },
            _good_event("b"),
            _good_event("c"),
        ],
        "endings_data": [_good_ending("A"), _good_ending("B")],
    }
    with pytest.raises(SchemaValidationError) as exc:
        validate_script_payload(payload)
    assert "disabled" in str(exc.value)


def test_script_with_too_few_endings_raises():
    payload = {
        "name": "test",
        "events_data": [_good_event("a"), _good_event("b"), _good_event("c")],
        "endings_data": [_good_ending("only")],
    }
    with pytest.raises(SchemaValidationError) as exc:
        validate_script_payload(payload)
    assert "endings_data" in str(exc.value)


def test_script_with_invalid_ending_type_enum_raises():
    payload = {
        "name": "test",
        "events_data": [_good_event("a"), _good_event("b"), _good_event("c")],
        "endings_data": [
            {**_good_ending("A"), "ending_type": "amazing"},
            _good_ending("B"),
        ],
    }
    with pytest.raises(SchemaValidationError):
        validate_script_payload(payload)


def test_valid_world_passes():
    payload = {
        "name": "雾港",
        "base_setting": "雾港位于海雾迷漫的港口城市",
        "free_setting": "",
    }
    validate_world_payload(payload)


def test_world_missing_base_setting_raises():
    with pytest.raises(SchemaValidationError) as exc:
        validate_world_payload({"name": "x", "base_setting": ""})
    assert "base_setting" in str(exc.value)
