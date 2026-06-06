from engine.state_manager import GameState
from engine.world_simulator import _process_structural_milestones


def _state(**kw):
    base = dict(current_time="第1天·上午", current_location="主厅", round_number=7)
    base.update(kw)
    return GameState(**base)


def test_milestone_commits_when_condition_met():
    s = _state()
    s.world_state = {"huafei_disgraced": 1}
    world = {"structural_milestones": [
        {"milestone_id": "m1", "fact_key": "alive.huafei", "fact_text": "华妃已赐死。",
         "kind": "entity_removed", "target_ref": "年世兰",
         "trigger": {"condition_dsl": "world_state.huafei_disgraced == 1"}},
    ]}
    _process_structural_milestones(s, world)
    assert any(f["fact_key"] == "alive.huafei" for f in s.structural_facts)


def test_milestone_skipped_when_condition_unmet():
    s = _state()
    s.world_state = {"huafei_disgraced": 0}
    world = {"structural_milestones": [
        {"milestone_id": "m1", "fact_key": "alive.huafei", "fact_text": "华妃已赐死。",
         "kind": "entity_removed", "target_ref": "年世兰",
         "trigger": {"condition_dsl": "world_state.huafei_disgraced == 1"}},
    ]}
    _process_structural_milestones(s, world)
    assert s.structural_facts == []


def test_milestone_not_recommitted_when_already_in_ledger():
    s = _state()
    s.world_state = {"flag": 1}
    world = {"structural_milestones": [
        {"milestone_id": "m1", "fact_key": "k", "fact_text": "事已成。",
         "kind": "world_fact_changed", "target_ref": None,
         "trigger": {"condition_dsl": "world_state.flag == 1"}},
    ]}
    _process_structural_milestones(s, world)
    _process_structural_milestones(s, world)  # second tick
    assert len([f for f in s.structural_facts if f["fact_key"] == "k"]) == 1


def test_milestone_bad_dsl_is_skipped_not_raised():
    s = _state()
    world = {"structural_milestones": [
        {"milestone_id": "m1", "fact_key": "k", "fact_text": "x", "kind": "world_fact_changed",
         "trigger": {"condition_dsl": "this is not valid ((("}},
    ]}
    _process_structural_milestones(s, world)  # must not raise
    assert s.structural_facts == []
