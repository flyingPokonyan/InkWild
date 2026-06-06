"""P1 §4: the weak-input clamp used to be all suppression (no NPC, short prose),
with no "advance the world but don't act for the player" middle gear — so weak
turns produced beautiful but inert scenes (0 progress). Pin that the hint now
carries the middle gear + a sensory payoff for pure observation."""
from engine.player_input_guard import assess_input_strength


def test_weak_hint_keeps_world_progression_clause():
    hint = assess_input_strength("环顾").to_hint()
    # middle gear present
    assert "推进世界" in hint or "环境线索" in hint
    # suppression clause still present (don't act for the player)
    assert "替玩家" in hint


def test_pure_observation_demands_sensory_payoff():
    assessment = assess_input_strength("仔细观察四周")
    assert assessment.is_pure_observation is True
    hint = assessment.to_hint()
    assert "感官" in hint or "看到" in hint


def test_normal_input_has_no_clamp_hint():
    # A directed action should not be flagged weak → empty hint, no clamp.
    assessment = assess_input_strength("我走向华妃，质问她关于香料的事")
    assert assessment.is_weak is False
    assert assessment.to_hint() == ""
