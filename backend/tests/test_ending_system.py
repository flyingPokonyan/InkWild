from engine.ending_system import check_hard_endings, merge_ai_ending_judgment
from engine.state_manager import GameState


ENDINGS = [
    {
        "id": "end_timeout",
        "ending_type": "timeout",
        "title": "时间耗尽",
        "priority": 10,
        "hard_conditions": {"type": "time", "max_time_index": 25},
        "soft_conditions": None,
    },
    {
        "id": "end_perfect",
        "ending_type": "perfect",
        "title": "真相大白",
        "priority": 5,
        "hard_conditions": None,
        "soft_conditions": "玩家正确指认凶手并给出合理动机",
    },
    {
        "id": "end_bad",
        "ending_type": "bad",
        "title": "凶手逃脱",
        "priority": 8,
        "hard_conditions": {"type": "time", "max_time_index": 25},
        "soft_conditions": None,
    },
]


def make_state(**overrides) -> GameState:
    defaults = {
        "current_time": "第1天·上午",
        "current_location": "镇口",
        "time_index": 0,
        "player_inventory": [],
        "discovered_clues": [],
        "npc_relations": {},
        "triggered_events": [],
    }
    defaults.update(overrides)
    return GameState(**defaults)


def test_timeout_triggers():
    state = make_state(time_index=26)
    ending = check_hard_endings(ENDINGS, state)

    assert ending is not None
    assert ending["ending_type"] == "timeout"


def test_no_hard_ending():
    state = make_state(time_index=10)
    ending = check_hard_endings(ENDINGS, state)

    assert ending is None


def test_ai_judgment_accepted():
    ai_judgment = {"should_end": True, "ending_type": "perfect", "reason": "玩家正确指认了凶手"}
    ending = merge_ai_ending_judgment(ENDINGS, ai_judgment)

    assert ending is not None
    assert ending["ending_type"] == "perfect"


def test_ai_judgment_rejected_no_match():
    ai_judgment = {"should_end": True, "ending_type": "nonexistent", "reason": "??"}
    ending = merge_ai_ending_judgment(ENDINGS, ai_judgment)

    assert ending is None


def test_ai_judgment_matches_with_surrounding_whitespace():
    # Director earned the ending but the type came back with stray whitespace.
    # Previously a silent drop → player fell through to the stall consolation.
    # Now trim-resilient so the earned good ending still resolves.
    ai_judgment = {"should_end": True, "ending_type": " perfect ", "reason": "玩家指认了凶手"}
    ending = merge_ai_ending_judgment(ENDINGS, ai_judgment)

    assert ending is not None
    assert ending["ending_type"] == "perfect"


def test_ai_no_end():
    ai_judgment = {"should_end": False}
    ending = merge_ai_ending_judgment(ENDINGS, ai_judgment)

    assert ending is None


ROUND_ENDINGS = [
    {
        "id": "end_max_rounds",
        "ending_type": "timeout",
        "title": "不了了之",
        "priority": 5,
        "hard_conditions": {"type": "max_rounds", "max_rounds": 100},
        "soft_conditions": None,
    },
    {
        "id": "end_stale",
        "ending_type": "bad",
        "title": "调查停滞",
        "priority": 8,
        "hard_conditions": {"type": "rounds_without_progress", "min_rounds": 20, "after_round": 40},
        "soft_conditions": None,
    },
]


def test_max_rounds_triggers():
    state = make_state(round_number=100)
    ending = check_hard_endings(ROUND_ENDINGS, state)
    assert ending is not None
    assert ending["ending_type"] == "timeout"


def test_max_rounds_not_yet():
    state = make_state(round_number=50)
    ending = check_hard_endings(ROUND_ENDINGS, state)
    # Only timeout has max_rounds=100, not reached; stale needs after_round=40 check
    assert ending is None


def test_rounds_without_progress_ending():
    state = make_state(round_number=45, rounds_since_last_clue=20)
    ending = check_hard_endings(ROUND_ENDINGS, state)
    assert ending is not None
    assert ending["ending_type"] == "bad"


def test_rounds_without_progress_before_after_round():
    state = make_state(round_number=30, rounds_since_last_clue=25)
    ending = check_hard_endings(ROUND_ENDINGS, state)
    # rounds_since_last_clue >= 20 but round_number < after_round(40)
    assert ending is None


# --- Phase 2.A.4: climax resolution controller ---------------------------------

from engine.ending_system import check_forced_ending
from engine.narrative_arc import (
    FORCED_AFTER_ROUND,
    FORCED_CLIMAX_LINGER_ROUNDS,
    FORCED_NO_PROGRESS_ROUNDS,
    RES_TIER_DECISION,
    RES_TIER_NONE,
    RES_TIER_PRESSURE,
    resolution_tier,
)

_ENDINGS = [
    {"ending_type": "good", "title": "圆满", "soft_conditions": "x", "priority": 8},
    {"ending_type": "normal", "title": "平淡", "soft_conditions": "y", "priority": 5},
    {"ending_type": "bad", "title": "崩坏", "soft_conditions": "z", "priority": 3},
]


def _state(**kw):
    base = dict(current_time="第1天·清晨", current_location="大厅", time_index=0, round_number=0)
    base.update(kw)
    return GameState(**base)


def test_resolution_tier_progression():
    assert resolution_tier("middle", 0) == RES_TIER_NONE
    assert resolution_tier("climax", 1) == RES_TIER_PRESSURE
    assert resolution_tier("climax", 6) == RES_TIER_DECISION


def test_forced_ending_fires_on_no_progress_stall():
    state = _state(round_number=FORCED_AFTER_ROUND + 1, rounds_since_last_clue=FORCED_NO_PROGRESS_ROUNDS)
    ending = check_forced_ending(_ENDINGS, state, "script")
    assert ending is not None
    # prefers normal/bad over the "earned" good outcome
    assert ending["ending_type"] in {"normal", "bad", "timeout"}


def test_forced_ending_fires_on_climax_linger():
    state = _state(round_number=5, rounds_since_last_clue=0, rounds_in_climax=FORCED_CLIMAX_LINGER_ROUNDS)
    assert check_forced_ending(_ENDINGS, state, "script") is not None


def test_forced_ending_quiet_when_progressing():
    state = _state(round_number=30, rounds_since_last_clue=1, rounds_in_climax=3)
    assert check_forced_ending(_ENDINGS, state, "script") is None


def test_forced_ending_never_in_free_mode():
    state = _state(round_number=99, rounds_since_last_clue=99, rounds_in_climax=99)
    assert check_forced_ending(_ENDINGS, state, "free") is None


def test_forced_ending_respects_after_round_floor():
    # stalled on clues but too early → don't cut off a fast opening
    state = _state(round_number=FORCED_AFTER_ROUND - 1, rounds_since_last_clue=FORCED_NO_PROGRESS_ROUNDS)
    assert check_forced_ending(_ENDINGS, state, "script") is None
