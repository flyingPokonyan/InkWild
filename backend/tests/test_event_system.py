from engine.event_system import check_events
from engine.state_manager import GameState


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


EVENTS = [
    {
        "id": "evt_001",
        "name": "第二次失踪",
        "trigger_type": "time",
        "trigger_condition": {"min_time_index": 10},
        "effects": {"add_clues": ["药铺后门有挣扎痕迹"]},
        "mode": "script_only",
    },
    {
        "id": "evt_002",
        "name": "管家露馅",
        "trigger_type": "clue",
        "trigger_condition": {"required_clues": ["clue_001"]},
        "effects": {"npc_updates": {"管家王福": {"mood": "慌张"}}},
        "mode": "both",
    },
    {
        "id": "evt_003",
        "name": "到达后山",
        "trigger_type": "location",
        "trigger_condition": {"location": "后山"},
        "effects": {"add_clues": ["发现新鲜脚印"]},
        "mode": "both",
    },
]


def test_time_event_triggers():
    state = make_state(time_index=10)
    triggered = check_events(EVENTS, state, game_mode="script")
    assert any(event["id"] == "evt_001" for event in triggered)


def test_time_event_not_yet():
    state = make_state(time_index=5)
    triggered = check_events(EVENTS, state, game_mode="script")
    assert not any(event["id"] == "evt_001" for event in triggered)


def test_clue_event_triggers():
    state = make_state(discovered_clues=[{"id": "clue_001", "content": "test", "found_at": "第1天"}])
    triggered = check_events(EVENTS, state, game_mode="script")
    assert any(event["id"] == "evt_002" for event in triggered)


def test_location_event_triggers():
    state = make_state(current_location="后山")
    triggered = check_events(EVENTS, state, game_mode="script")
    assert any(event["id"] == "evt_003" for event in triggered)


def test_already_triggered_skipped():
    state = make_state(time_index=10, triggered_events=["evt_001"])
    triggered = check_events(EVENTS, state, game_mode="script")
    assert not any(event["id"] == "evt_001" for event in triggered)


def test_mode_filter():
    state = make_state(time_index=10)
    triggered = check_events(EVENTS, state, game_mode="free")
    assert not any(event["id"] == "evt_001" for event in triggered)


CLUE_COUNT_EVENT = {
    "id": "evt_clue_count",
    "name": "管家露馅(线索数)",
    "trigger_type": "clue_count",
    "trigger_condition": {"min_clues_found": 3},
    "effects": {},
    "mode": "both",
}

ROUNDS_WITHOUT_PROGRESS_EVENT = {
    "id": "evt_stale",
    "name": "NPC搭话",
    "trigger_type": "rounds_without_progress",
    "trigger_condition": {"min_rounds": 8},
    "effects": {"add_clues": ["有人看到管家深夜出门"]},
    "mode": "both",
}


def test_clue_count_triggers():
    clues = [{"id": f"clue_{i}", "content": f"线索{i}", "found_at": ""} for i in range(3)]
    state = make_state(discovered_clues=clues)
    triggered = check_events([CLUE_COUNT_EVENT], state, game_mode="script")
    assert any(e["id"] == "evt_clue_count" for e in triggered)


def test_clue_count_not_enough():
    clues = [{"id": "clue_1", "content": "线索1", "found_at": ""}]
    state = make_state(discovered_clues=clues)
    triggered = check_events([CLUE_COUNT_EVENT], state, game_mode="script")
    assert not any(e["id"] == "evt_clue_count" for e in triggered)


def test_rounds_without_progress_triggers():
    state = make_state(rounds_since_last_clue=8)
    triggered = check_events([ROUNDS_WITHOUT_PROGRESS_EVENT], state, game_mode="script")
    assert any(e["id"] == "evt_stale" for e in triggered)


def test_rounds_without_progress_not_yet():
    state = make_state(rounds_since_last_clue=5)
    triggered = check_events([ROUNDS_WITHOUT_PROGRESS_EVENT], state, game_mode="script")
    assert not any(e["id"] == "evt_stale" for e in triggered)
