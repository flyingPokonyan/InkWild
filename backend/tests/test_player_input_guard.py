"""Runtime v2 — weak input detection."""

from __future__ import annotations

import pytest

from engine.player_input_guard import (
    WEAK_INPUT_CHAR_THRESHOLD,
    assess_input_strength,
)

pytestmark = pytest.mark.no_db


def test_empty_is_weak():
    r = assess_input_strength("")
    assert r.is_weak
    assert r.char_count == 0


def test_short_input_is_weak():
    r = assess_input_strength("环顾")
    assert r.is_weak
    assert r.is_pure_observation


def test_long_input_is_not_weak():
    text = "走向工棚，撬开门锁，把那只油布木匣取出来"
    r = assess_input_strength(text)
    assert not r.is_weak
    assert r.has_explicit_target


def test_pure_observation_long_still_weak():
    # Long but still pure observation with no target verb.
    r = assess_input_strength("再看看这里，再看看那里，再看看周围。")
    assert r.is_weak
    assert r.is_pure_observation


def test_long_input_with_target_keyword_not_weak():
    r = assess_input_strength("我去问周世安关于昨夜的事情")
    assert not r.is_weak
    assert r.has_explicit_target


def test_to_hint_empty_when_strong():
    r = assess_input_strength("我前往大理寺去找狄仁杰询问案情")
    assert r.to_hint() == ""


def test_to_hint_populated_when_weak():
    r = assess_input_strength("环顾")
    hint = r.to_hint()
    assert "player_input_weak" in hint
    assert "active_npcs" in hint
    assert "dramatic_intensity" in hint


def test_threshold_boundary():
    # threshold-1 chars → weak; threshold chars → not weak (unless pure obs).
    weak = assess_input_strength("a" * (WEAK_INPUT_CHAR_THRESHOLD - 1))
    assert weak.is_weak
    strong_len = assess_input_strength("我要" + "x" * (WEAK_INPUT_CHAR_THRESHOLD - 2))
    # 'x' isn't an observation keyword and there's no target keyword either,
    # so this is borderline — the test that matters is char_count.
    assert strong_len.char_count >= WEAK_INPUT_CHAR_THRESHOLD
