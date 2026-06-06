"""Integration tests for NPC Agent v2 field injection (§7.1).

Tests that build_npc_system (in engine.prompts) correctly renders the three
new v2 fields — relevant_lore, involved_shared_events, relevant_rumors — and
that empty fields produce no stray section headings.
"""

from __future__ import annotations

import pytest

from engine.prompts import build_npc_system


def _build(**overrides) -> str:
    """Helper: call build_npc_system with sensible defaults, allow overrides."""
    defaults = dict(
        npc_name="梅长苏",
        npc_personality="谋士，深沉内敛",
        npc_secret=None,
        instruction="按角色回应玩家。",
        memories=[],
        trust=5,
        mood="正常",
        relevant_lore=None,
        involved_shared_events=None,
        relevant_rumors=None,
    )
    defaults.update(overrides)
    return build_npc_system(**defaults)


def test_npc_system_includes_relevant_lore():
    """relevant_lore non-empty → prompt contains block content."""
    prompt = _build(
        relevant_lore=[
            {
                "key": "schools",
                "name": "门派",
                "heading": "江左盟",
                "body": "盟主梅长苏，精于谋略。",
            },
        ],
    )
    assert "江左盟" in prompt or "门派" in prompt
    assert "盟主梅长苏" in prompt


def test_npc_system_includes_shared_events_perception():
    """involved_shared_events non-empty → prompt contains event title and knows text."""
    prompt = _build(
        npc_name="A",
        involved_shared_events=[
            {
                "id": "e1",
                "title": "赤焰旧案",
                "summary": "S",
                "knows": "我亲历",
                "believes": "",
                "feels": "悲愤",
            },
        ],
    )
    assert "赤焰旧案" in prompt
    assert "我亲历" in prompt
    assert "悲愤" in prompt


def test_npc_system_includes_rumors():
    """relevant_rumors non-empty → prompt contains rumour text and section heading."""
    prompt = _build(
        npc_name="A",
        relevant_rumors=["听说誉王最近频繁出入礼部"],
    )
    assert "誉王" in prompt
    # Section heading must mention 传闻
    assert "传闻" in prompt


def test_npc_system_skips_empty_v2_fields():
    """All three v2 fields empty → no bare section headings left dangling."""
    prompt = _build(
        relevant_lore=[],
        involved_shared_events=[],
        relevant_rumors=[],
    )
    # Section headings should not appear when lists are empty
    assert "相关世界规则" not in prompt
    assert "涉及你的过往事件" not in prompt
    assert "你听说的传闻" not in prompt


def test_npc_system_skips_none_v2_fields():
    """None v2 fields → same behaviour as empty lists."""
    prompt = _build(
        relevant_lore=None,
        involved_shared_events=None,
        relevant_rumors=None,
    )
    assert "相关世界规则" not in prompt
    assert "涉及你的过往事件" not in prompt
    assert "你听说的传闻" not in prompt


def test_npc_system_shared_events_knows_only():
    """Optional sub-fields: only 'knows' set → believes/feels lines absent."""
    prompt = _build(
        npc_name="B",
        involved_shared_events=[
            {
                "id": "e2",
                "title": "密谋",
                "summary": "密谋细节",
                "knows": "知情内容",
                "believes": "",
                "feels": "",
            }
        ],
    )
    assert "密谋" in prompt
    assert "知情内容" in prompt
    # Empty believes/feels should not create spurious lines
    assert "你相信：" not in prompt
    assert "你的感受：" not in prompt


def test_npc_system_multiple_rumors():
    """Multiple rumors are all rendered."""
    prompt = _build(
        npc_name="C",
        relevant_rumors=["传言一", "传言二", "传言三"],
    )
    assert "传言一" in prompt
    assert "传言二" in prompt
    assert "传言三" in prompt


def test_npc_system_existing_params_unchanged():
    """Existing parameters (world_setting, knowledge, reflection) still work
    correctly when v2 fields are also provided."""
    prompt = _build(
        world_setting="明朝末年",
        knowledge=["皇帝信任奸臣"],
        reflection="我必须隐忍。",
        relevant_lore=[{"key": "k", "name": "n", "heading": "朝局", "body": "严党把持朝纲"}],
        relevant_rumors=["海瑞将上疏"],
    )
    assert "明朝末年" in prompt
    assert "皇帝信任奸臣" in prompt
    assert "我必须隐忍。" in prompt
    assert "朝局" in prompt
    assert "海瑞将上疏" in prompt
