"""Phase 2 tests: events_data_builder consumes structured condition_tree."""
from services.events_data_builder import _validate_event


CHAR_NAMES = {"林怀瑾", "苏婉", "陈默"}


def test_tree_input_is_accepted_and_serialized():
    """LLM emits structured condition_tree; validator serializes to DSL string."""
    raw = {
        "id": "evt_001",
        "kind": "conditional",
        "summary": "时间到达 day_3 且玩家发现真相",
        "trigger": {
            "condition_tree": {
                "op": "AND",
                "operands": [
                    {"op": "func", "name": "time_after", "args": ["day_3"]},
                    {"op": "==", "left": {"field": "world_state.discovered"}, "right": True},
                ],
            },
            "probability": 0.8,
        },
        "effects": {"world_state_changes": {}, "spawn_clues": [], "npc_mood_changes": {}},
        "rumors": [],
    }
    entry = _validate_event(raw, CHAR_NAMES)
    assert entry.disabled is False
    assert "time_after('day_3')" in entry.trigger["condition_dsl"]
    # Tree is preserved for audit.
    assert entry.trigger.get("condition_tree") is not None


def test_invalid_tree_disables_event_with_clear_reason():
    raw = {
        "id": "evt_002",
        "kind": "conditional",
        "summary": "bad tree",
        "trigger": {
            "condition_tree": {"op": "XOR", "operands": []},
            "probability": 0.5,
        },
        "effects": {},
        "rumors": [],
    }
    entry = _validate_event(raw, CHAR_NAMES)
    assert entry.disabled is True
    assert "XOR" in entry.disabled_reason or "unknown op" in entry.disabled_reason


def test_legacy_string_dsl_still_accepted_when_valid():
    """Transition compat: pre-tree generations with valid DSL still parse."""
    raw = {
        "id": "evt_003",
        "kind": "conditional",
        "summary": "legacy",
        "trigger": {
            "condition_dsl": "time_after('day_2')",
            "probability": 1.0,
        },
        "effects": {},
        "rumors": [],
    }
    entry = _validate_event(raw, CHAR_NAMES)
    assert entry.disabled is False


def test_legacy_bare_flag_string_disables_event():
    """The whole reason we're moving to trees: bare-flag DSL must fail loudly."""
    raw = {
        "id": "evt_004",
        "kind": "conditional",
        "summary": "bad legacy",
        "trigger": {
            "condition_dsl": "world_state.x AND world_state.y",
            "probability": 1.0,
        },
        "effects": {},
        "rumors": [],
    }
    entry = _validate_event(raw, CHAR_NAMES)
    assert entry.disabled is True


def test_npc_intent_with_tree():
    raw = {
        "id": "evt_005",
        "kind": "npc_intent_driven",
        "summary": "NPC intent triggers",
        "trigger": {
            "npc_name": "林怀瑾",
            "condition_tree": {"op": "func", "name": "location_is", "args": ["朝堂"]},
            "intent_payload": {},
        },
        "effects": {},
        "rumors": [],
    }
    entry = _validate_event(raw, CHAR_NAMES)
    assert entry.disabled is False
    assert entry.trigger["condition_dsl"] == "location_is('朝堂')"


def test_unknown_npc_name_still_disables():
    """Tree validation passes but invalid npc_name still disables."""
    raw = {
        "id": "evt_006",
        "kind": "npc_intent_driven",
        "summary": "unknown npc",
        "trigger": {
            "npc_name": "路人甲",
            "condition_tree": {"op": "func", "name": "time_after", "args": ["day_1"]},
            "intent_payload": {},
        },
        "effects": {},
        "rumors": [],
    }
    entry = _validate_event(raw, CHAR_NAMES)
    assert entry.disabled is True
    assert "invalid_npc_name" in entry.disabled_reason
