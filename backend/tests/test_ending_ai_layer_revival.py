"""P1 §3 regression: once the director's `ending_triggered` survives truncation
(Task 1+2), the AI ending layer must pick the EARNED ending instead of letting
the session fall through to the stall floor's consolation prize. Pins
merge_ai_ending_judgment so the layer can't silently die again."""
from engine.ending_system import merge_ai_ending_judgment


def _endings():
    return [
        {"ending_type": "good", "priority": 10, "soft_conditions": {"any": []},
         "title": "真相大白"},
        {"ending_type": "timeout", "priority": 1, "soft_conditions": {"any": []},
         "title": "不了了之"},
    ]


def test_ai_judgment_selects_earned_ending():
    ai = {"should_end": True, "ending_type": "good", "reason": "玩家揭穿真凶"}
    picked = merge_ai_ending_judgment(_endings(), ai)
    assert picked is not None
    assert picked["ending_type"] == "good"


def test_ai_judgment_should_not_end_returns_none():
    assert merge_ai_ending_judgment(_endings(), {"should_end": False}) is None


def test_ai_judgment_unknown_type_returns_none():
    ai = {"should_end": True, "ending_type": "does_not_exist"}
    assert merge_ai_ending_judgment(_endings(), ai) is None
