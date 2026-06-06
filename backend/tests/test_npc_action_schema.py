"""Runtime v2 — NPCAction schema + validator (no LLM, no DB)."""

from __future__ import annotations

import pytest

from engine.npc_action import (
    ACTION_TYPES,
    NPCAction,
    validate_action,
)

pytestmark = pytest.mark.no_db


def test_speak_minimal_ok():
    action = validate_action(
        "周世安",
        {"action_type": "speak", "priority": 6, "dialogue": "你来得正好。"},
    )
    assert not action.omitted
    assert action.action_type == "speak"
    assert action.priority == 6
    assert action.dialogue == "你来得正好。"


def test_speak_without_dialogue_is_omitted():
    action = validate_action(
        "周世安",
        {"action_type": "speak", "priority": 7},
    )
    assert action.omitted


def test_act_without_physical_is_omitted():
    action = validate_action(
        "周世安",
        {"action_type": "act", "priority": 7},
    )
    assert action.omitted


def test_act_with_physical_ok():
    action = validate_action(
        "周世安",
        {"action_type": "act", "priority": 7, "physical": "起身关上窗户"},
    )
    assert not action.omitted
    assert action.physical == "起身关上窗户"


def test_unknown_action_type_dropped():
    action = validate_action(
        "周世安",
        {"action_type": "yell", "priority": 5, "dialogue": "X"},
    )
    assert action.omitted
    # Validator picks a safe default action_type for the placeholder.
    assert action.action_type == "observe"


def test_priority_clamped_to_range():
    action = validate_action(
        "周世安",
        {"action_type": "speak", "priority": 99, "dialogue": "X"},
    )
    assert action.priority == 10
    action_low = validate_action(
        "周世安",
        {"action_type": "speak", "priority": -3, "dialogue": "X"},
    )
    assert action_low.priority == 1


def test_background_npc_priority_capped_at_5():
    action = validate_action(
        "乞丐",
        {"action_type": "speak", "priority": 9, "dialogue": "X"},
        scene_role="background",
    )
    assert action.priority == 5


def test_background_interject_demoted_to_observe():
    action = validate_action(
        "乞丐",
        {"action_type": "interject", "priority": 9, "dialogue": "等等！"},
        scene_role="background",
    )
    # Demoted, but observe doesn't carry dialogue — also stripped.
    assert action.action_type == "observe"
    assert action.dialogue == ""


def test_dialogue_truncated_at_400():
    long = "啊" * 600
    action = validate_action(
        "周世安",
        {"action_type": "speak", "priority": 5, "dialogue": long},
    )
    assert len(action.dialogue) == 400


def test_hidden_note_truncated_at_80():
    long = "我打算" * 60
    action = validate_action(
        "周世安",
        {
            "action_type": "scheme",
            "priority": 3,
            "hidden_note": long,
        },
    )
    assert len(action.hidden_note) == 80
    # scheme is internal; dialogue stripped (if any).
    assert action.dialogue == ""


def test_scheme_dialogue_stripped():
    action = validate_action(
        "周世安",
        {
            "action_type": "scheme",
            "priority": 2,
            "dialogue": "这话不该说",
            "hidden_note": "等他露出破绽再动手",
        },
    )
    assert action.dialogue == ""
    assert action.hidden_note == "等他露出破绽再动手"


def test_observe_dialogue_stripped():
    action = validate_action(
        "周世安",
        {
            "action_type": "observe",
            "priority": 3,
            "dialogue": "本不该说",
        },
    )
    assert action.dialogue == ""
    assert not action.omitted  # observe with no dialogue is fine


def test_target_npc_unknown_dropped():
    action = validate_action(
        "周世安",
        {
            "action_type": "speak",
            "priority": 5,
            "dialogue": "X",
            "target_npc": "陌生人",
        },
        known_npcs={"周世安", "李元芳"},
    )
    assert action.target_npc is None


def test_target_npc_known_kept():
    action = validate_action(
        "周世安",
        {
            "action_type": "speak",
            "priority": 5,
            "dialogue": "X",
            "target_npc": "李元芳",
        },
        known_npcs={"周世安", "李元芳"},
    )
    assert action.target_npc == "李元芳"


def test_intent_update_pivot_requires_new_goal():
    # pivot without new_goal is dropped.
    action = validate_action(
        "周世安",
        {
            "action_type": "speak",
            "priority": 5,
            "dialogue": "X",
            "intent_update": {"progress": "pivot"},
        },
    )
    assert action.intent_update is None


def test_intent_update_pivot_with_goal_ok():
    action = validate_action(
        "周世安",
        {
            "action_type": "speak",
            "priority": 5,
            "dialogue": "X",
            "intent_update": {"progress": "pivot", "new_goal": "保住吏部"},
        },
    )
    assert action.intent_update is not None
    assert action.intent_update.progress == "pivot"
    assert action.intent_update.new_goal == "保住吏部"


def test_intent_update_stuck_with_blocked_by():
    action = validate_action(
        "周世安",
        {
            "action_type": "withhold",
            "priority": 5,
            "dialogue": "我不清楚。",
            "intent_update": {"progress": "stuck", "blocked_by": "缺玩家信任"},
        },
    )
    assert action.intent_update is not None
    assert action.intent_update.blocked_by == "缺玩家信任"


def test_mood_shift_same_value_dropped():
    action = validate_action(
        "周世安",
        {
            "action_type": "speak",
            "priority": 5,
            "dialogue": "X",
            "mood_shift": {"from": "紧张", "to": "紧张", "reason": "X"},
        },
    )
    assert action.mood_shift is None


def test_mood_shift_proper():
    action = validate_action(
        "周世安",
        {
            "action_type": "speak",
            "priority": 5,
            "dialogue": "X",
            "mood_shift": {"from": "紧张", "to": "愤怒", "reason": "被识破"},
        },
    )
    assert action.mood_shift is not None
    assert action.mood_shift.to_mood == "愤怒"


def test_wait_for_self_dropped():
    action = validate_action(
        "周世安",
        {
            "action_type": "speak",
            "priority": 5,
            "dialogue": "X",
            "wait_for": "周世安",
        },
        active_npcs={"周世安", "李元芳"},
    )
    assert action.wait_for is None


def test_wait_for_outside_active_dropped():
    action = validate_action(
        "周世安",
        {
            "action_type": "speak",
            "priority": 5,
            "dialogue": "X",
            "wait_for": "狄仁杰",
        },
        active_npcs={"周世安", "李元芳"},
    )
    assert action.wait_for is None


def test_wait_for_valid_kept():
    action = validate_action(
        "周世安",
        {
            "action_type": "speak",
            "priority": 5,
            "dialogue": "X",
            "wait_for": "李元芳",
        },
        active_npcs={"周世安", "李元芳"},
    )
    assert action.wait_for == "李元芳"


def test_invalid_tone_falls_back_to_neutral():
    action = validate_action(
        "周世安",
        {
            "action_type": "speak",
            "priority": 5,
            "dialogue": "X",
            "tone": "psychotic",
        },
    )
    assert action.tone == "neutral"


def test_internal_action_tone_forced_neutral():
    action = validate_action(
        "周世安",
        {
            "action_type": "observe",
            "priority": 3,
            "tone": "deceptive",
        },
    )
    assert action.tone == "neutral"


def test_none_input_returns_omitted_observe():
    action = validate_action("周世安", None)
    assert action.omitted
    assert action.action_type == "observe"


def test_all_six_action_types_constructable():
    for at in ACTION_TYPES:
        raw = {"action_type": at, "priority": 5}
        if at in {"speak", "withhold", "interject"}:
            raw["dialogue"] = "示例"
        if at == "act":
            raw["physical"] = "示例动作"
        action = validate_action("X", raw)
        assert action.action_type == at, at


def test_is_visible_logic():
    speak = NPCAction(npc_name="A", action_type="speak", dialogue="hi")
    assert speak.is_visible()
    silent = NPCAction(npc_name="A", action_type="speak", dialogue="")
    silent.omitted = True
    assert not silent.is_visible()
    observe = NPCAction(npc_name="A", action_type="observe", hidden_note="z")
    assert not observe.is_visible()
    scheme = NPCAction(npc_name="A", action_type="scheme")
    assert not scheme.is_visible()
    act = NPCAction(npc_name="A", action_type="act", physical="转身")
    assert act.is_visible()
