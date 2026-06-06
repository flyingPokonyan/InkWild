import pytest
from services.world_critic_service import validate_world_shape


def test_no_violations_passes():
    payload = {
        "world_characters": [{"name": "A", "personality": "p", "schedule": {"morning": "loc1"}, "initial_location": "loc1"}],
        "playable": [{"name": "A"}],
        "locations": [{"name": "loc1"}],
    }
    warnings = validate_world_shape(payload)
    assert warnings == []


def test_playable_not_in_characters():
    payload = {
        "world_characters": [{"name": "A", "schedule": {}, "initial_location": ""}],
        "playable": [{"name": "GhostNPC"}],
        "locations": [],
    }
    warnings = validate_world_shape(payload)
    assert any("GhostNPC" in w for w in warnings)


def test_schedule_invalid_location():
    payload = {
        "world_characters": [{"name": "A", "schedule": {"noon": "ghost_loc"}, "initial_location": "loc1"}],
        "playable": [], "locations": [{"name": "loc1"}],
    }
    warnings = validate_world_shape(payload)
    assert any("ghost_loc" in w for w in warnings)


def test_initial_location_invalid():
    payload = {
        "world_characters": [{"name": "A", "schedule": {}, "initial_location": "ghost_loc"}],
        "playable": [], "locations": [{"name": "loc1"}],
    }
    warnings = validate_world_shape(payload)
    assert any("ghost_loc" in w for w in warnings)


def test_shared_events_invalid_npc():
    payload = {
        "world_characters": [{"name": "A", "schedule": {}, "initial_location": ""}],
        "playable": [], "locations": [],
        "shared_events": [{"id": "e1", "involved_npcs": ["A", "Ghost"]}],
    }
    warnings = validate_world_shape(payload)
    assert any("Ghost" in w for w in warnings)


def test_events_data_npc_intent_invalid_npc():
    payload = {
        "world_characters": [{"name": "A", "schedule": {}, "initial_location": ""}],
        "playable": [], "locations": [],
        "events_data": [{
            "id": "e1", "kind": "npc_intent_driven", "disabled": False,
            "trigger": {"npc_name": "Ghost"},
            "effects": {"npc_mood_changes": {}}, "rumors": [],
        }],
    }
    warnings = validate_world_shape(payload)
    assert any("Ghost" in w for w in warnings)


def test_events_data_disabled_skipped():
    """已 disabled 的 event 不再校验引用（避免重复 warn）"""
    payload = {
        "world_characters": [{"name": "A", "schedule": {}, "initial_location": ""}],
        "playable": [], "locations": [],
        "events_data": [{
            "id": "e1", "kind": "npc_intent_driven", "disabled": True,
            "trigger": {"npc_name": "Ghost"},
            "effects": {"npc_mood_changes": {}}, "rumors": [],
        }],
    }
    warnings = validate_world_shape(payload)
    assert warnings == []


def test_rumor_knower_invalid():
    payload = {
        "world_characters": [{"name": "A", "schedule": {}, "initial_location": ""}],
        "playable": [], "locations": [],
        "events_data": [{
            "id": "e1", "kind": "conditional", "disabled": False,
            "trigger": {"condition_dsl": "..."},
            "effects": {"npc_mood_changes": {}},
            "rumors": [{"text": "rumor", "knower_npcs": ["A", "Ghost"]}],
        }],
    }
    warnings = validate_world_shape(payload)
    assert any("Ghost" in w for w in warnings)


def test_npc_mood_changes_invalid_key():
    payload = {
        "world_characters": [{"name": "A", "schedule": {}, "initial_location": ""}],
        "playable": [], "locations": [],
        "events_data": [{
            "id": "e1", "kind": "conditional", "disabled": False,
            "trigger": {"condition_dsl": "..."},
            "effects": {"npc_mood_changes": {"A": "happy", "Ghost": "sad"}},
            "rumors": [],
        }],
    }
    warnings = validate_world_shape(payload)
    assert any("Ghost" in w for w in warnings)


def test_missing_optional_fields_no_violation():
    """payload 没有 events_data / shared_events / lore_pack 字段时不应报错"""
    payload = {
        "world_characters": [{"name": "A", "schedule": {}, "initial_location": ""}],
        "playable": [{"name": "A"}],
        "locations": [],
    }
    warnings = validate_world_shape(payload)
    assert warnings == []
