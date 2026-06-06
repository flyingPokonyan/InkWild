"""Pin the dynamic clue_id constraint Director's case_board_ops gets.

Director kept inventing IDs like CLUE_001 / c1 / comment_timestamp_anomaly
through 2026-05-23. The fix is not a JSON-Schema enum (clue_id is a data
key inside open-typed match/value, not a typed property) but an explicit
list embedded in the tool description string.
"""
from __future__ import annotations

from engine.prompts import build_director_tool


def test_explicit_clue_id_list_embedded_when_present():
    tool = build_director_tool(
        script_type="mystery",
        game_mode="script",
        discovered_clue_ids=["clue_alpha", "clue_beta"],
    )
    description = tool["input_schema"]["properties"]["case_board_ops"]["description"]
    assert "clue_alpha" in description
    assert "clue_beta" in description
    assert "仅允许使用的 clue_id" in description


def test_empty_clues_directs_to_new_clues_first():
    tool = build_director_tool(
        script_type="mystery",
        game_mode="script",
        discovered_clue_ids=[],
    )
    description = tool["input_schema"]["properties"]["case_board_ops"]["description"]
    assert "state_updates.new_clues" in description
    assert "仅允许使用的 clue_id" not in description


def test_free_mode_has_no_case_board_at_all():
    tool = build_director_tool(
        script_type="", game_mode="free", discovered_clue_ids=["x"],
    )
    assert "case_board_ops" not in tool["input_schema"]["properties"]
