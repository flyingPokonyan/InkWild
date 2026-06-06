"""Structured condition tree used by the generator pipeline.

Generators emit a JSON tree; we serialize it to the existing DSL string
(condition_dsl.py syntax) for storage and runtime evaluation. The runtime
evaluator is unchanged — this module exists only at the generator boundary.

Allowed shapes::

    {"op": "func", "name": "time_after" | "location_is" | "player_did", "args": [str]}
    {"op": "==" | "!=" | ">=" | "<=" | ">" | "<",
     "left":  {"field": "world_state.<key>"} | <int>,
     "right": <int> | <bool> | {"field": "world_state.<key>"}}
    {"op": "AND" | "OR", "operands": [<node>, <node>, ...]}     # >= 2 operands
    {"op": "NOT", "operand": <node>}
"""

from __future__ import annotations

from typing import Any

ConditionTree = dict[str, Any]


class ConditionTreeError(ValueError):
    """Raised on malformed tree at serialize time."""


_ALLOWED_FUNCS = {
    "time_after": 1,
    "location_is": 1,
    "player_did": 1,
}
_ALLOWED_CMP = {"==", "!=", ">=", "<=", ">", "<"}


def _is_field(node: Any) -> bool:
    return isinstance(node, dict) and "field" in node and len(node) == 1


def _serialize_operand(node: Any) -> str:
    if isinstance(node, bool):
        return "1" if node else "0"
    if isinstance(node, int):
        return str(node)
    if isinstance(node, str):
        # String literals serialize to single-quoted form. DSL grammar
        # bars embedded single quotes in STRING tokens, so reject those
        # rather than emit invalid DSL.
        if "'" in node:
            raise ConditionTreeError(
                f"single quote in string literal unsupported: {node!r}"
            )
        return f"'{node}'"
    if _is_field(node):
        field = str(node["field"])
        if not field.startswith("world_state."):
            raise ConditionTreeError(f"field must start with world_state.: {field!r}")
        return field
    raise ConditionTreeError(f"unsupported operand: {node!r}")


def _quote(s: str) -> str:
    if "'" in s:
        raise ConditionTreeError(f"single quote in func arg unsupported: {s!r}")
    return f"'{s}'"


def serialize_to_dsl(tree: ConditionTree) -> str:
    """Serialize *tree* into the existing DSL string format.

    Raises ConditionTreeError on malformed input.
    """
    if not isinstance(tree, dict) or "op" not in tree:
        raise ConditionTreeError(f"tree node must be a dict with 'op': {tree!r}")

    op = tree["op"]

    if op == "func":
        name = tree.get("name")
        args = tree.get("args") or []
        if name not in _ALLOWED_FUNCS:
            raise ConditionTreeError(f"unknown function: {name!r}")
        if len(args) != _ALLOWED_FUNCS[name]:
            raise ConditionTreeError(
                f"function {name!r} expects {_ALLOWED_FUNCS[name]} arg(s), got {len(args)}"
            )
        return f"{name}({', '.join(_quote(str(a)) for a in args)})"

    if op in _ALLOWED_CMP:
        left = _serialize_operand(tree.get("left"))
        right = _serialize_operand(tree.get("right"))
        return f"{left} {op} {right}"

    if op in {"AND", "OR"}:
        operands = tree.get("operands") or []
        if len(operands) < 2:
            raise ConditionTreeError(f"{op} requires >= 2 operands")
        parts = [f"({serialize_to_dsl(o)})" for o in operands]
        return f" {op} ".join(parts)

    if op == "NOT":
        operand = tree.get("operand")
        if operand is None:
            raise ConditionTreeError("NOT requires 'operand'")
        return f"NOT ({serialize_to_dsl(operand)})"

    raise ConditionTreeError(f"unknown op: {op!r}")


def validate_tree(
    tree: ConditionTree,
    *,
    allowed_world_state_keys: set[str] | None = None,
) -> list[str]:
    """Walk *tree*, collect human-readable issues. Returns empty list on success."""
    issues: list[str] = []
    _walk(tree, allowed_world_state_keys, issues, path="$")
    return issues


def _walk(
    node: Any,
    allowed_keys: set[str] | None,
    issues: list[str],
    *,
    path: str,
) -> None:
    if not isinstance(node, dict) or "op" not in node:
        issues.append(f"{path}: node must be dict with 'op'")
        return
    op = node["op"]
    if op == "func":
        name = node.get("name")
        args = node.get("args") or []
        if name not in _ALLOWED_FUNCS:
            issues.append(f"{path}: unknown function {name!r}; allowed={sorted(_ALLOWED_FUNCS)}")
            return
        if len(args) != _ALLOWED_FUNCS[name]:
            issues.append(
                f"{path}: function {name!r} expects {_ALLOWED_FUNCS[name]} arg(s), got {len(args)}"
            )
    elif op in _ALLOWED_CMP:
        for side in ("left", "right"):
            val = node.get(side)
            if _is_field(val):
                field = str(val["field"])
                if not field.startswith("world_state."):
                    issues.append(f"{path}.{side}: field must start with world_state.")
                    continue
                key = field.split(".", 1)[1]
                if allowed_keys is not None and key not in allowed_keys:
                    issues.append(
                        f"{path}.{side}: unknown world_state key {key!r}; allowed={sorted(allowed_keys)}"
                    )
            elif not isinstance(val, (int, bool, str)):
                issues.append(f"{path}.{side}: must be int / bool / str / field-ref")
    elif op in {"AND", "OR"}:
        operands = node.get("operands") or []
        if len(operands) < 2:
            issues.append(f"{path}: {op} requires >= 2 operands")
        for i, child in enumerate(operands):
            _walk(child, allowed_keys, issues, path=f"{path}.operands[{i}]")
    elif op == "NOT":
        child = node.get("operand")
        if child is None:
            issues.append(f"{path}: NOT requires 'operand'")
        else:
            _walk(child, allowed_keys, issues, path=f"{path}.operand")
    else:
        issues.append(f"{path}: unknown op {op!r}")
