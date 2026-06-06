import pytest
from engine.condition_tree import (
    ConditionTreeError,
    serialize_to_dsl,
    validate_tree,
)
from engine.condition_dsl import parse as dsl_parse


def test_serialize_func_call():
    tree = {"op": "func", "name": "time_after", "args": ["day_3"]}
    assert serialize_to_dsl(tree) == "time_after('day_3')"


def test_serialize_field_comparison_bool_true():
    tree = {"op": "==", "left": {"field": "world_state.discovered"}, "right": True}
    # Booleans encoded as 1/0 to match existing evaluator semantics.
    assert serialize_to_dsl(tree) == "world_state.discovered == 1"


def test_serialize_field_comparison_int():
    tree = {"op": ">=", "left": {"field": "world_state.tech"}, "right": 3}
    assert serialize_to_dsl(tree) == "world_state.tech >= 3"


def test_serialize_and_or_not_roundtrips_through_parser():
    tree = {
        "op": "AND",
        "operands": [
            {"op": "func", "name": "time_after", "args": ["day_2"]},
            {
                "op": "OR",
                "operands": [
                    {"op": "func", "name": "location_is", "args": ["朝堂"]},
                    {"op": "NOT", "operand": {"op": "func", "name": "location_is", "args": ["密室"]}},
                ],
            },
        ],
    }
    dsl = serialize_to_dsl(tree)
    assert "AND" in dsl and "OR" in dsl and "NOT" in dsl
    # And it must round-trip through the existing parser without errors.
    dsl_parse(dsl)


def test_serialize_rejects_unknown_op():
    with pytest.raises(ConditionTreeError):
        serialize_to_dsl({"op": "XOR", "operands": []})


def test_serialize_rejects_and_with_one_operand():
    with pytest.raises(ConditionTreeError):
        serialize_to_dsl(
            {"op": "AND", "operands": [{"op": "func", "name": "time_after", "args": ["day_1"]}]}
        )


def test_serialize_rejects_field_outside_world_state():
    with pytest.raises(ConditionTreeError):
        serialize_to_dsl({"op": "==", "left": {"field": "case_board.x"}, "right": 1})


def test_validate_unknown_field_with_allowed_keys():
    tree = {"op": "==", "left": {"field": "world_state.unknown_flag"}, "right": True}
    errors = validate_tree(tree, allowed_world_state_keys={"discovered", "met_lead"})
    assert errors and "unknown_flag" in errors[0]


def test_validate_unknown_function():
    tree = {"op": "func", "name": "weather_is", "args": ["sunny"]}
    errors = validate_tree(tree)
    assert errors and "weather_is" in errors[0]


def test_validate_func_arg_count():
    tree = {"op": "func", "name": "time_after", "args": []}
    errors = validate_tree(tree)
    assert errors and "time_after" in errors[0]


def test_validate_clean_tree_returns_no_errors():
    tree = {
        "op": "AND",
        "operands": [
            {"op": "func", "name": "time_after", "args": ["day_3"]},
            {"op": "==", "left": {"field": "world_state.discovered"}, "right": True},
        ],
    }
    assert validate_tree(tree) == []


def test_validate_accepts_string_literal_rhs():
    """String literals on comparison sides are legal (smoke-issues-2026-05-23-1225.md).
    Pre-fix the validator rejected world_state.scene == 'garden' with
    `must be int / bool / field-ref`, which barred a normal pattern the
    LLM emits when scenes/flags are string-valued.
    """
    tree = {
        "op": "==",
        "left": {"field": "world_state.scene"},
        "right": "garden",
    }
    assert validate_tree(tree) == []


def test_serialize_string_literal_quotes_value():
    """The serializer wraps the literal in single quotes so the DSL
    evaluator's STRING token recognizes it.
    """
    from engine.condition_tree import serialize_to_dsl
    tree = {
        "op": "==",
        "left": {"field": "world_state.scene"},
        "right": "garden",
    }
    assert serialize_to_dsl(tree) == "world_state.scene == 'garden'"
