"""Runtime v2 — director output validators."""

from __future__ import annotations

import pytest

from engine.director_validator import (
    check_focus_objectivity,
    validate_active_npcs,
    validate_event_fire_intent,
    validate_offstage_active,
    validate_per_npc_focus,
    validate_scene_role,
)

pytestmark = pytest.mark.no_db


def test_directive_words_detected():
    leak = check_focus_objectivity("X", "你应该保持冷静，试图回避追问")
    assert "应该" in leak
    assert "保持" in leak
    assert "试图" in leak


def test_objective_focus_clean():
    leak = check_focus_objectivity("X", "玩家直接对你说话，目光锁定你的桌案")
    assert leak == []


def test_active_npcs_drops_unknown():
    out = validate_active_npcs(["周世安", "幽灵"], known_npcs={"周世安", "李元芳"})
    assert out == ["周世安"]


def test_active_npcs_truncated_at_4():
    out = validate_active_npcs(
        ["A", "B", "C", "D", "E"],
        known_npcs={"A", "B", "C", "D", "E"},
    )
    assert len(out) == 4
    assert out == ["A", "B", "C", "D"]


def test_active_npcs_dedupe_preserves_order():
    out = validate_active_npcs(
        ["A", "B", "A", "C"],
        known_npcs={"A", "B", "C"},
    )
    assert out == ["A", "B", "C"]


def test_per_npc_focus_fills_missing():
    out = validate_per_npc_focus({"周世安": "玩家直视你"}, ["周世安", "李元芳"])
    assert out["周世安"] == "玩家直视你"
    assert out["李元芳"] == "在场"


def test_per_npc_focus_drops_inactive():
    out = validate_per_npc_focus(
        {"周世安": "X", "陌生人": "Y"},
        ["周世安"],
    )
    assert "陌生人" not in out


def test_per_npc_focus_trims_long_text():
    long = "a" * 200
    out = validate_per_npc_focus({"周世安": long}, ["周世安"])
    assert len(out["周世安"]) <= 120


def test_scene_role_fills_missing_secondary():
    out = validate_scene_role(
        {"周世安": "primary"},
        ["周世安", "李元芳"],
        valid_roles={"primary", "secondary", "background"},
    )
    assert out["周世安"] == "primary"
    assert out["李元芳"] == "secondary"


def test_scene_role_invalid_falls_back():
    out = validate_scene_role(
        {"周世安": "main_lead"},
        ["周世安"],
        valid_roles={"primary", "secondary", "background"},
    )
    assert out["周世安"] == "secondary"


def test_offstage_drops_active_overlap():
    out = validate_offstage_active(
        ["周世安", "李元芳"],
        active_npcs=["周世安"],
        known_npcs={"周世安", "李元芳"},
    )
    assert "周世安" not in out
    assert out == ["李元芳"]


def test_offstage_drops_unknown():
    out = validate_offstage_active(
        ["陌生人"],
        active_npcs=[],
        known_npcs={"A", "B"},
    )
    assert out == []


def test_event_fire_intent_drops_already_fired():
    out = validate_event_fire_intent(
        ["evt_1", "evt_2"],
        fired_ids={"evt_1"},
        known_event_ids={"evt_1", "evt_2"},
    )
    assert out == ["evt_2"]


def test_event_fire_intent_drops_unknown():
    out = validate_event_fire_intent(
        ["evt_nonexistent"],
        fired_ids=set(),
        known_event_ids={"evt_1"},
    )
    assert out == []


def test_event_fire_intent_preserves_order():
    out = validate_event_fire_intent(
        ["evt_3", "evt_1", "evt_2"],
        fired_ids=set(),
        known_event_ids={"evt_1", "evt_2", "evt_3"},
    )
    assert out == ["evt_3", "evt_1", "evt_2"]
