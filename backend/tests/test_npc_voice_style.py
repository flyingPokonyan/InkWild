"""build_npc_system / _v2 voice_style + IP guardrails.

Guards the two hard constraints from spec 2026-06-01:
- voice_style + guardrails live in the STABLE prefix (before per-turn/volatile
  content) → prompt prefix cache stays intact.
- empty/None voice_style → no voice block (legacy rows render byte-identical).
"""
from engine.prompts import (
    _NPC_IP_SAFETY_GUARDRAILS,
    build_npc_system,
    build_npc_system_v2,
)

GUARD0 = _NPC_IP_SAFETY_GUARDRAILS[0]
VOICE = "自称「本宫」；爱用反问与威压。范例：「这后宫之中，还轮不到你说话。」"


def test_v1_voice_style_in_stable_prefix():
    s = build_npc_system(
        npc_name="华妃",
        npc_personality="跋扈",
        npc_secret=None,
        instruction="回应玩家",
        voice_style=VOICE,
        scene_context={"current_time": "午后"},  # volatile
        memories=[{"round_number": 1, "content": "x"}],  # volatile
    )
    assert "## 你的说话方式" in s
    assert "还轮不到你说话" in s
    # voice block must precede the per-turn (volatile) sections → stays cached
    assert s.index("## 你的说话方式") < s.index("## 当前场景")
    assert s.index("## 你的说话方式") < s.index("## 你的记忆")


def test_v1_empty_voice_style_no_block_keeps_guardrails():
    s = build_npc_system(
        npc_name="A", npc_personality="p", npc_secret=None, instruction="i",
        voice_style=None,
    )
    assert "## 你的说话方式" not in s
    assert GUARD0 in s  # guardrails always on


def test_v1_guardrails_in_stable_prefix():
    s = build_npc_system(
        npc_name="A", npc_personality="p", npc_secret=None, instruction="i",
        scene_context={"current_time": "午后"},
    )
    assert GUARD0 in s
    assert s.index(GUARD0) < s.index("## 当前场景")


def test_v2_voice_style_and_guardrails_stable():
    s = build_npc_system_v2(
        npc_name="华妃", npc_personality="跋扈", npc_secret=None,
        voice_style=VOICE, scene_role="primary",
    )
    assert "## 你的说话方式" in s
    assert "还轮不到你说话" in s
    # v2 volatile section begins at "## 本回合你的戏份位置"
    assert s.index("## 你的说话方式") < s.index("## 本回合你的戏份位置")
    assert GUARD0 in s
    assert s.index(GUARD0) < s.index("## 本回合你的戏份位置")


def test_v2_empty_voice_style_no_block():
    s = build_npc_system_v2(
        npc_name="A", npc_personality="p", npc_secret=None,
        voice_style="", scene_role="secondary",
    )
    assert "## 你的说话方式" not in s
    assert GUARD0 in s
