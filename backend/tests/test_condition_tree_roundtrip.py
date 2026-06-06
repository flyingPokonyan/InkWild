"""Round-trip: tree -> DSL string -> existing parser -> evaluator.

The generator-side tree must produce DSL that the unchanged runtime
evaluator (engine/condition_dsl.py) accepts and evaluates correctly.

The evaluator reads game_state via these attribute/dict-key names:
- `current_time` (e.g. "day_5"), used by time_after()
- `current_location`, used by location_is()
- `player_actions`, used by player_did()
- `world_state` dict, used by world_state.<key> comparisons
"""
import pytest
from engine.condition_tree import serialize_to_dsl
from engine.condition_dsl import parse, evaluate


def _state(world_state=None, location="朝堂", time="day_5", actions=None):
    return {
        "world_state": world_state or {},
        "current_location": location,
        "current_time": time,
        "player_actions": actions or [],
    }


@pytest.mark.parametrize("tree,state,expected", [
    (
        {"op": "func", "name": "time_after", "args": ["day_3"]},
        _state(time="day_5"),
        True,
    ),
    (
        {"op": "func", "name": "time_after", "args": ["day_5"]},
        _state(time="day_2"),
        False,
    ),
    (
        {"op": "==", "left": {"field": "world_state.discovered"}, "right": True},
        _state({"discovered": 1}),
        True,
    ),
    (
        {"op": "==", "left": {"field": "world_state.discovered"}, "right": True},
        _state({"discovered": 0}),
        False,
    ),
    (
        {"op": ">=", "left": {"field": "world_state.tech"}, "right": 3},
        _state({"tech": 5}),
        True,
    ),
    (
        {
            "op": "AND",
            "operands": [
                {"op": "func", "name": "time_after", "args": ["day_3"]},
                {"op": "==", "left": {"field": "world_state.met_lead"}, "right": True},
            ],
        },
        _state({"met_lead": 1}, time="day_4"),
        True,
    ),
    (
        {
            "op": "NOT",
            "operand": {"op": "func", "name": "location_is", "args": ["密室"]},
        },
        _state(location="朝堂"),
        True,
    ),
    (
        {"op": "func", "name": "player_did", "args": ["翻阅日志"]},
        _state(actions=["翻阅日志", "审问嫌犯"]),
        True,
    ),
])
def test_tree_roundtrip(tree, state, expected):
    dsl = serialize_to_dsl(tree)
    parsed = parse(dsl)
    assert evaluate(parsed, state) is expected
