"""Runtime v2 — GameState new fields round-trip + config flag wiring."""

from __future__ import annotations

import pytest

from config import settings
from engine.state_manager import GameState

pytestmark = pytest.mark.no_db


def test_runtime_v2_flag_is_boolean():
    """Sanity check that the flag is wired and boolean-typed. The actual
    default was flipped to True on 2026-05-25 after v2 went live; this test
    just guards against accidental rename / type drift."""
    assert isinstance(settings.runtime_architecture_v2_enabled, bool)


def test_new_state_fields_default_empty():
    state = GameState(current_time="day_1·上午", current_location="家")
    assert state.last_active_round == {}
    assert state.pending_player_segments == []
    assert state.offstage_event_log == {}


def test_state_to_from_dict_round_trip():
    state = GameState(
        current_time="day_2·下午",
        current_location="大理寺",
        last_active_round={"周世安": 5, "李元芳": 7},
        pending_player_segments=["藏入怀中", "回大理寺"],
        offstage_event_log={
            "周世安": [{"round": 3, "content": "玩家提到你", "source": "李元芳"}]
        },
    )
    payload = state.to_dict()
    assert payload["last_active_round"] == {"周世安": 5, "李元芳": 7}
    assert payload["pending_player_segments"] == ["藏入怀中", "回大理寺"]
    assert "周世安" in payload["offstage_event_log"]

    restored = GameState.from_dict(payload)
    assert restored.last_active_round == state.last_active_round
    assert restored.pending_player_segments == state.pending_player_segments
    assert restored.offstage_event_log == state.offstage_event_log


def test_legacy_state_dict_without_v2_fields_loads():
    """Older sessions in the DB don't have the v2 fields. from_dict must
    default them rather than raise."""
    legacy = {
        "current_time": "day_1·上午",
        "current_location": "家",
        "round_number": 5,
    }
    restored = GameState.from_dict(legacy)
    assert restored.last_active_round == {}
    assert restored.pending_player_segments == []
    assert restored.offstage_event_log == {}


def test_new_config_flags_present():
    # Just smoke-check the flag exists with the right default; the orchestrator
    # reads these by name so a rename would silently break the v2 path.
    assert settings.npc_offstage_tick_rounds == 7
    assert settings.npc_action_max_tools_per_call == 1
    assert settings.npc_climax_step_timeout_seconds == 45.0
    assert settings.runtime_v2_thinking_call_cap == 15
