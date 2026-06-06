"""Runtime v2 — multi-step player action segmentation."""

from __future__ import annotations

import pytest

from engine.action_segmentation import (
    MAX_SEGMENTS,
    consume_pending_segment,
    segment_player_action,
)

pytestmark = pytest.mark.no_db


def test_empty_returns_empty_list():
    assert segment_player_action("") == []
    assert segment_player_action(None) == []
    assert segment_player_action("   ") == []


def test_single_step_returns_one_entry():
    out = segment_player_action("环顾四周")
    assert out == ["环顾四周"]


def test_arrow_splits():
    out = segment_player_action("取匣 → 藏入怀中 → 回大理寺再细察")
    assert len(out) == 3
    assert out[0].startswith("取匣")
    assert "藏入" in out[1]
    assert "大理寺" in out[2]


def test_halfwidth_arrow_splits():
    out = segment_player_action("A -> B => C")
    assert len(out) == 3
    assert out == ["A", "B", "C"]


def test_numbered_list_splits():
    out = segment_player_action("1. 进屋 2. 翻账本 3. 退出")
    assert len(out) == 3
    assert "进屋" in out[0]
    assert "翻账本" in out[1]
    assert "退出" in out[2]


def test_numbered_list_with_chinese_punctuation():
    out = segment_player_action("1、看信件 2、问管家")
    assert len(out) == 2


def test_particle_split_with_enough_content():
    out = segment_player_action("先去东厢看看然后回正堂问周世安")
    # Should split on "然后" because both sides ≥ 4 chars.
    assert len(out) == 2
    assert "东厢" in out[0]
    assert "周世安" in out[1]


def test_particle_split_rejects_short_sides():
    # "再" with insufficient content shouldn't split.
    out = segment_player_action("看再")
    assert out == ["看再"]


def test_max_segments_cap():
    long_input = " → ".join([f"step{i}" for i in range(8)])
    out = segment_player_action(long_input)
    assert len(out) <= MAX_SEGMENTS


def test_consume_pending_with_continue_pops_head():
    pending = ["藏入怀中", "回大理寺再细察"]
    effective, new_pending, used = consume_pending_segment(pending, "继续")
    assert used is True
    assert effective == "藏入怀中"
    assert new_pending == ["回大理寺再细察"]


def test_consume_pending_with_empty_input_pops_head():
    pending = ["藏入怀中"]
    effective, new_pending, used = consume_pending_segment(pending, "")
    assert used is True
    assert effective == "藏入怀中"
    assert new_pending == []


def test_consume_pending_with_substantive_input_clears():
    pending = ["藏入怀中", "回大理寺再细察"]
    effective, new_pending, used = consume_pending_segment(
        pending, "我改主意，先去问周世安"
    )
    assert used is False
    assert effective == "我改主意，先去问周世安"
    assert new_pending == []


def test_consume_pending_empty_pending_empty_input():
    effective, new_pending, used = consume_pending_segment([], "")
    assert used is False
    assert effective is None
    assert new_pending == []
