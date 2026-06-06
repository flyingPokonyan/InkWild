import pytest

from engine.case_board import InvalidClueRefError, apply_case_board_ops
from schemas.case_board import CaseBoardOp


def test_upsert_adds_evidence_with_known_clue_id() -> None:
    game_state = {"discovered_clues": [{"id": "c1", "content": "Blood stain", "found_at": "study"}]}
    board = {"evidence": []}
    ops = [
        CaseBoardOp(
            op_type="upsert_list_item",
            path=["evidence"],
            match={"clue_id": "c1"},
            value={"clue_id": "c1", "label": "Study stain", "weight": "high"},
            reason="Anchor evidence to discovered clue",
        )
    ]

    new_board, history = apply_case_board_ops(game_state, board, ops)

    assert new_board == {"evidence": [{"clue_id": "c1", "label": "Study stain", "weight": "high"}]}
    assert board == {"evidence": []}
    assert history == [
        {
            "op_type": "upsert_list_item",
            "path": ["evidence"],
            "payload": {
                "match": {"clue_id": "c1"},
                "value": {"clue_id": "c1", "label": "Study stain", "weight": "high"},
            },
            "reason": "Anchor evidence to discovered clue",
            "before": None,
            "after": {"clue_id": "c1", "label": "Study stain", "weight": "high"},
        }
    ]


def test_unknown_clue_id_is_rejected_recursively() -> None:
    game_state = {"discovered_clues": [{"id": "c1"}]}
    ops = [
        {
            "op_type": "upsert_list_item",
            "path": ["evidence"],
            "match": {"nested": {"clue_id": "missing"}},
            "value": {"clue_id": "c1"},
        }
    ]

    with pytest.raises(InvalidClueRefError):
        apply_case_board_ops(game_state, {}, ops)


def test_non_string_clue_id_is_rejected_as_case_board_error() -> None:
    game_state = {"discovered_clues": [{"id": "c1"}]}
    ops = [
        {
            "op_type": "upsert_list_item",
            "path": ["evidence"],
            "match": {"clue_id": "c1"},
            "value": {"clue_id": ["c1"]},
        }
    ]

    with pytest.raises(InvalidClueRefError):
        apply_case_board_ops(game_state, {}, ops)


def test_upsert_updates_existing_suspect() -> None:
    game_state = {"discovered_clues": []}
    board = {"suspects": [{"id": "s1", "name": "Lin", "status": "unknown"}]}
    ops = [
        {
            "op_type": "upsert_list_item",
            "path": ["suspects"],
            "match": {"id": "s1"},
            "value": {"status": "cleared"},
            "reason": "Alibi confirmed",
        }
    ]

    new_board, history = apply_case_board_ops(game_state, board, ops)

    assert new_board["suspects"] == [{"id": "s1", "name": "Lin", "status": "cleared"}]
    assert history[0]["before"] == {"id": "s1", "name": "Lin", "status": "unknown"}
    assert history[0]["after"] == {"id": "s1", "name": "Lin", "status": "cleared"}


def test_remove_list_item() -> None:
    game_state = {"discovered_clues": []}
    board = {"threads": [{"id": "t1"}, {"id": "t2"}]}
    ops = [{"op_type": "remove_list_item", "path": ["threads"], "match": {"id": "t1"}}]

    new_board, history = apply_case_board_ops(game_state, board, ops)

    assert new_board == {"threads": [{"id": "t2"}]}
    assert history[0]["before"] == {"id": "t1"}
    assert history[0]["after"] is None


def test_set_field() -> None:
    game_state = {"discovered_clues": []}
    board = {"summary": {"status": "open"}}
    ops = [{"op_type": "set_field", "path": ["summary", "status"], "value": "resolved"}]

    new_board, history = apply_case_board_ops(game_state, board, ops)

    assert new_board == {"summary": {"status": "resolved"}}
    assert history[0] == {
        "op_type": "set_field",
        "path": ["summary", "status"],
        "payload": {"match": {}, "value": "resolved"},
        "reason": None,
        "before": "open",
        "after": "resolved",
    }
