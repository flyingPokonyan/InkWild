"""Phase 3 tests: endings generator produces full runtime-compatible shape."""
import pytest
from services.world_creator_agent_v2 import _validate_ending_payload


def test_validate_complete_ending_passes():
    ending = {
        "ending_type": "good",
        "title": "真相大白",
        "description": "玩家揭开真相，正义得到伸张。" * 4,
        "soft_conditions": "玩家在 day_5 前发现关键线索",
        "priority": 1,
        "quality": "best",
    }
    assert _validate_ending_payload(ending) == []


def test_missing_ending_type_returns_issue():
    ending = {
        "title": "真相大白",
        "description": "...",
        "soft_conditions": "...",
        "priority": 1,
        "quality": "best",
    }
    issues = _validate_ending_payload(ending)
    assert any("ending_type" in i for i in issues)


def test_missing_title_returns_issue():
    ending = {
        "ending_type": "good",
        "description": "...",
        "soft_conditions": "...",
        "priority": 1,
    }
    issues = _validate_ending_payload(ending)
    assert any("title" in i for i in issues)


def test_invalid_ending_type_enum():
    ending = {
        "ending_type": "amazing",
        "title": "t",
        "description": "d",
        "soft_conditions": "s",
        "priority": 1,
        "quality": "best",
    }
    issues = _validate_ending_payload(ending)
    assert any("ending_type" in i and "amazing" in i for i in issues)


def test_missing_soft_conditions_returns_issue():
    ending = {
        "ending_type": "good",
        "title": "t",
        "description": "d",
        "priority": 1,
        "quality": "best",
    }
    issues = _validate_ending_payload(ending)
    assert any("soft_conditions" in i for i in issues)


def test_priority_must_be_int():
    ending = {
        "ending_type": "good",
        "title": "t",
        "description": "d",
        "soft_conditions": "s",
        "priority": "high",
        "quality": "best",
    }
    issues = _validate_ending_payload(ending)
    assert any("priority" in i for i in issues)


def test_empty_string_required_field_is_caught():
    """Missing-or-empty: empty strings count as missing."""
    ending = {
        "ending_type": "",
        "title": "t",
        "description": "d",
        "soft_conditions": "s",
        "priority": 0,
    }
    issues = _validate_ending_payload(ending)
    assert any("ending_type" in i for i in issues)
