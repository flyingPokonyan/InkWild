"""Initial NPC→player stance inference — parsing/validation.

The LLM call itself is integration; here we pin the pure parse+clamp logic:
known names only, trust clamped to [0,10], mood/note sanitised, garbage → {}.
"""
from __future__ import annotations

from engine.stance_inference import parse_stances

_NAMES = {"皇后宜修", "沈眉庄", "华妃年世兰"}


def test_parses_valid_and_clamps_trust():
    raw = (
        '{"stances":['
        '{"npc":"皇后宜修","trust":1,"mood":"戒备","note":"视她为夺宠劲敌"},'
        '{"npc":"沈眉庄","trust":15,"mood":"亲近","note":"自幼情同姐妹"},'
        '{"npc":"华妃年世兰","trust":-5,"mood":"敌意","note":"新晋威胁"}]}'
    )
    out = parse_stances(raw, _NAMES)
    assert out["皇后宜修"] == {"trust": 1, "mood": "戒备", "note": "视她为夺宠劲敌"}
    assert out["沈眉庄"]["trust"] == 10   # clamped from 15
    assert out["华妃年世兰"]["trust"] == 0  # clamped from -5


def test_drops_unknown_names():
    raw = '{"stances":[{"npc":"路人甲","trust":3,"mood":"正常","note":"x"}]}'
    assert parse_stances(raw, _NAMES) == {}


def test_strips_code_fence():
    raw = '```json\n{"stances":[{"npc":"沈眉庄","trust":7,"mood":"亲近","note":"挚友"}]}\n```'
    out = parse_stances(raw, _NAMES)
    assert out["沈眉庄"]["trust"] == 7


def test_garbage_returns_empty():
    assert parse_stances("not json at all", _NAMES) == {}
    assert parse_stances("", _NAMES) == {}


def test_missing_fields_default_safely():
    raw = '{"stances":[{"npc":"皇后宜修"}]}'  # no trust/mood/note
    out = parse_stances(raw, _NAMES)
    assert out["皇后宜修"]["trust"] == 3
    assert out["皇后宜修"]["mood"] == "正常"
    assert out["皇后宜修"]["note"] == ""
