"""Regression: WorldCreatorAgentV2 prompts the LLM for a string difficulty
(``"easy|medium|hard"``), but ``worlds.difficulty`` is ``smallint``. Without
coercion, publishing a v2-generated world raises ``asyncpg.DataError:
invalid input for query argument ... 'medium' ('str' object cannot be
interpreted as an integer)``.
"""

import pytest

from api import admin as admin_api


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("easy", 2),
        ("medium", 3),
        ("hard", 4),
        ("Medium", 3),
        ("MEDIUM", 3),
        (1, 1),
        (3, 3),
        (5, 5),
        ("3", 3),
        ("99", 3),
        (None, 3),
        ("nonsense", 3),
    ],
)
def test_normalize_world_difficulty_coerced_to_int(raw, expected):
    payload = {} if raw is None else {"difficulty": raw}
    out = admin_api._normalize_world_payload(payload)
    assert isinstance(out["difficulty"], int)
    assert out["difficulty"] == expected


def test_normalize_world_characters_null_fields_coerced():
    """world_characters.initial_location / personality / knowledge etc. are
    NOT NULL columns. LLM sometimes emits ``null`` for them, but
    ``dict.get(key, default)`` returns None when the key is present with a
    None value (not the default). The normalizer must coerce nulls to safe
    defaults so publishing never raises NotNullViolationError.
    """
    payload = {
        "world_characters": [
            {
                "name": "ChunkyCharacter",
                "personality": None,
                "knowledge": None,
                "schedule": None,
                "initial_location": None,
                "playable": None,
                "abilities": None,
                "starting_inventory": None,
            }
        ]
    }
    out = admin_api._normalize_world_payload(payload)
    assert len(out["world_characters"]) == 1
    c = out["world_characters"][0]
    assert c["name"] == "ChunkyCharacter"
    assert c["personality"] == ""
    assert c["initial_location"] == ""
    assert c["knowledge"] == []
    assert c["schedule"] == {}
    assert c["abilities"] == []
    assert c["starting_inventory"] == []
    assert c["playable"] is False


def test_normalize_world_characters_uses_top_level_playable_list():
    """v2 agent emits ``playable`` as a top-level list of names and leaves
    ``world_characters[*].playable`` unset (Character schema has no such field).
    Normalize must cross-reference the two so DB ends up with the playable flag
    on the right characters. Names not in the list stay non-playable.
    """
    payload = {
        "playable": [
            {"name": "韩立", "role_tag": "主角", "description": "..."},
            {"name": "南宫婉", "role_tag": "天命道侣", "description": "..."},
        ],
        "world_characters": [
            {"name": "韩立", "personality": "p"},
            {"name": "南宫婉", "personality": "p"},
            {"name": "墨大夫", "personality": "p"},
        ],
    }
    out = admin_api._normalize_world_payload(payload)
    by_name = {c["name"]: c for c in out["world_characters"]}
    assert by_name["韩立"]["playable"] is True
    assert by_name["南宫婉"]["playable"] is True
    assert by_name["墨大夫"]["playable"] is False


def test_normalize_world_characters_preserves_valid_fields():
    payload = {
        "world_characters": [
            {
                "name": "Fan",
                "personality": "guarded",
                "initial_location": "雪落镇",
                "playable": True,
                "knowledge": ["k1", "k2"],
                "schedule": {"morning": "shop"},
                "abilities": ["butchering"],
                "starting_inventory": ["cleaver"],
                "secret": "hidden",
                "description": "屠户女",
                "avatar": "https://example.com/a.png",
                "initial_peer_relations": {"Xie": "wary"},
            }
        ]
    }
    out = admin_api._normalize_world_payload(payload)
    c = out["world_characters"][0]
    assert c["initial_location"] == "雪落镇"
    assert c["playable"] is True
    assert c["knowledge"] == ["k1", "k2"]
    assert c["secret"] == "hidden"
    assert c["initial_peer_relations"] == {"Xie": "wary"}
