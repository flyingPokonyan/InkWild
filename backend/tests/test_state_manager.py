from engine.state_manager import GameState, apply_state_updates


def make_initial_state() -> GameState:
    return GameState(
        current_time="第1天·上午",
        current_location="镇口",
        player_inventory=["笔记本"],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        time_index=0,
    )


def test_apply_location_update():
    state = make_initial_state()
    updates = {"location": "茶摊"}
    new_state = apply_state_updates(state, updates)

    assert new_state.current_location == "茶摊"


def test_apply_time_advance():
    state = make_initial_state()
    updates = {"time_advance": True}
    new_state = apply_state_updates(state, updates)

    assert new_state.current_time == "第1天·下午"
    assert new_state.time_index == 1


def test_apply_new_clues():
    state = make_initial_state()
    updates = {"new_clues": ["死者手中有铜扣"]}
    new_state = apply_state_updates(state, updates)

    assert len(new_state.discovered_clues) == 1
    assert new_state.discovered_clues[0]["content"] == "死者手中有铜扣"


def test_apply_npc_updates():
    state = make_initial_state()
    state.npc_relations = {"管家王福": {"trust": 3, "mood": "正常", "last_interaction": ""}}
    updates = {"npc_updates": {"管家王福": {"trust_change": -1, "mood": "紧张"}}}
    new_state = apply_state_updates(state, updates)

    assert new_state.npc_relations["管家王福"]["trust"] == 2
    assert new_state.npc_relations["管家王福"]["mood"] == "紧张"


def test_apply_inventory_changes():
    state = make_initial_state()
    updates = {"inventory_changes": {"add": ["放大镜"], "remove": []}}
    new_state = apply_state_updates(state, updates)

    assert "放大镜" in new_state.player_inventory


def test_no_time_advance():
    state = make_initial_state()
    updates = {"time_advance": False}
    new_state = apply_state_updates(state, updates)

    assert new_state.current_time == "第1天·上午"
    assert new_state.time_index == 0


def test_round_number_increments():
    state = make_initial_state()
    new_state = apply_state_updates(state, {})
    assert new_state.round_number == 1

    new_state2 = apply_state_updates(new_state, {})
    assert new_state2.round_number == 2


def test_rounds_since_last_clue_resets_on_new_clue():
    state = make_initial_state()
    state.rounds_since_last_clue = 5

    new_state = apply_state_updates(state, {"new_clues": ["找到了一把钥匙"]})
    assert new_state.rounds_since_last_clue == 0


def test_rounds_since_last_clue_increments_without_clue():
    state = make_initial_state()
    new_state = apply_state_updates(state, {})
    assert new_state.rounds_since_last_clue == 1

    new_state2 = apply_state_updates(new_state, {"location": "茶摊"})
    assert new_state2.rounds_since_last_clue == 2
