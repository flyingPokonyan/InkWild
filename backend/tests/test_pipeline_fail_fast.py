"""Pin the fail-fast gates that skip image generation when content is
below publishable thresholds. Addresses the 嘉靖宫变前夜 budget-waste
case in smoke-issues-2026-05-23-1225.md.
"""
from __future__ import annotations

from services.world_creator_agent_v2 import (
    _MIN_CHARACTERS,
    _MIN_EVENTS_DATA,
    _check_min_content,
)


def test_below_minimum_returns_warning_event():
    warning = _check_min_content(
        phase="character_roster",
        count=0,
        minimum=_MIN_CHARACTERS,
        code="character_count_below_minimum",
        what="角色数量",
    )
    assert warning is not None
    assert warning["code"] == "character_count_below_minimum"
    assert warning["meta"]["aborted"] is True
    assert "0 < 3" in warning["message"]


def test_at_or_above_minimum_returns_none():
    assert _check_min_content(
        phase="character_roster",
        count=_MIN_CHARACTERS,
        minimum=_MIN_CHARACTERS,
        code="x",
        what="x",
    ) is None
    assert _check_min_content(
        phase="events_data",
        count=_MIN_EVENTS_DATA + 1,
        minimum=_MIN_EVENTS_DATA,
        code="x",
        what="x",
    ) is None
