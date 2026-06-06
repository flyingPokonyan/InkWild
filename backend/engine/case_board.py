from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from schemas.case_board import CaseBoardHistoryEntry, CaseBoardOp


class CaseBoardError(ValueError):
    pass


class InvalidClueRefError(CaseBoardError):
    pass


class InvalidCaseBoardOpError(CaseBoardError):
    pass


def apply_case_board_ops(
    game_state: dict,
    current_board: dict | None,
    ops: list[CaseBoardOp | dict],
) -> tuple[dict, list[dict]]:
    board = deepcopy(current_board) if current_board is not None else {}
    if not isinstance(board, dict):
        raise InvalidCaseBoardOpError("current_board must be a dict or None")

    discovered_ids = _discovered_clue_ids(game_state)
    normalized_ops = [_coerce_op(op) for op in ops]
    history: list[dict] = []

    for op in normalized_ops:
        _validate_clue_refs(op, discovered_ids)

        if op.op_type == "set_field":
            before, after = _apply_set_field(board, op)
        elif op.op_type == "upsert_list_item":
            before, after = _apply_upsert_list_item(board, op)
        elif op.op_type == "remove_list_item":
            before, after = _apply_remove_list_item(board, op)
        else:
            raise InvalidCaseBoardOpError(f"Unsupported case board op: {op.op_type}")

        history.append(
            CaseBoardHistoryEntry(
                op_type=op.op_type,
                path=op.path,
                payload={"match": op.match, "value": op.value},
                reason=op.reason,
                before=before,
                after=after,
            ).model_dump()
        )

    return board, history


def _coerce_op(op: CaseBoardOp | dict) -> CaseBoardOp:
    if isinstance(op, CaseBoardOp):
        return op
    try:
        return CaseBoardOp.model_validate(op)
    except ValidationError as exc:
        raise InvalidCaseBoardOpError(str(exc)) from exc


def _discovered_clue_ids(game_state: dict) -> set[str]:
    return {
        clue["id"]
        for clue in game_state.get("discovered_clues", [])
        if isinstance(clue, dict) and isinstance(clue.get("id"), str)
    }


def _validate_clue_refs(op: CaseBoardOp, discovered_ids: set[str]) -> None:
    for clue_id in _iter_clue_ids(op.match):
        if clue_id not in discovered_ids:
            raise InvalidClueRefError(f"Unknown clue_id: {clue_id}")
    for clue_id in _iter_clue_ids(op.value):
        if clue_id not in discovered_ids:
            raise InvalidClueRefError(f"Unknown clue_id: {clue_id}")


def _iter_clue_ids(value: Any) -> list[str]:
    clue_ids: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "clue_id":
                if not isinstance(child, str):
                    raise InvalidClueRefError("clue_id must be a string")
                clue_ids.append(child)
                continue
            clue_ids.extend(_iter_clue_ids(child))
    elif isinstance(value, list):
        for child in value:
            clue_ids.extend(_iter_clue_ids(child))
    return clue_ids


def _apply_set_field(board: dict, op: CaseBoardOp) -> tuple[Any, Any]:
    parent = _resolve_parent_dict(board, op.path, create=True)
    key = op.path[-1]
    before = deepcopy(parent.get(key))
    parent[key] = deepcopy(op.value)
    return before, deepcopy(parent[key])


def _apply_upsert_list_item(board: dict, op: CaseBoardOp) -> tuple[Any, Any]:
    items = _resolve_list_target(board, op.path, create=True)
    value = deepcopy(op.value)
    if not isinstance(value, dict):
        raise InvalidCaseBoardOpError("upsert_list_item requires dict value")

    for item in items:
        if _matches(item, op.match):
            before = deepcopy(item)
            item.update(value)
            return before, deepcopy(item)

    items.append(value)
    return None, deepcopy(value)


def _apply_remove_list_item(board: dict, op: CaseBoardOp) -> tuple[Any, Any]:
    try:
        items = _resolve_list_target(board, op.path, create=False)
    except InvalidCaseBoardOpError:
        return None, None
    for index, item in enumerate(items):
        if _matches(item, op.match):
            before = deepcopy(item)
            del items[index]
            return before, None
    return None, None


def _resolve_parent_dict(board: dict, path: list[str], *, create: bool = False) -> dict:
    current = board
    for part in path[:-1]:
        child = current.get(part)
        if child is None and create:
            child = {}
            current[part] = child
        elif not isinstance(child, dict):
            raise InvalidCaseBoardOpError(f"path component is not a dict: {part}")
        current = child
    return current


def _resolve_list_target(board: dict, path: list[str], create: bool) -> list:
    parent = _resolve_parent_dict(board, path, create=create)
    key = path[-1]
    target = parent.get(key)
    if target is None and create:
        target = []
        parent[key] = target
    if not isinstance(target, list):
        raise InvalidCaseBoardOpError(f"path target is not a list: {key}")
    return target


def _matches(item: Any, match: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    return all(item.get(key) == value for key, value in match.items())
