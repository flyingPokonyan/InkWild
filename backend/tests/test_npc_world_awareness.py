"""NPC world / scene / knowledge / intent awareness in build_npc_system.

Covers the four context blocks added so the NPC has basic in-character
grounding instead of treating every turn as a context-free prompt.
"""
from __future__ import annotations

from engine.prompts import build_npc_system


def _base_kwargs(**overrides) -> dict:
    base = dict(
        npc_name="王福",
        npc_personality="忠厚寡言",
        npc_secret=None,
        instruction="回应玩家",
    )
    base.update(overrides)
    return base


def test_world_setting_appears_in_stable_prefix():
    text = build_npc_system(
        **_base_kwargs(world_setting="民国二十三年的湘西雾隐镇，雾气常年不散。")
    )
    assert "你所在的世界" in text
    assert "民国二十三年" in text
    # Stable prefix: appears before per-turn variable suffix sections.
    assert text.index("民国二十三年") < text.index("行为规则")


def test_knowledge_appears_when_provided():
    text = build_npc_system(
        **_base_kwargs(knowledge=["你为老爷工作 30 年", "你识字但不识洋文"])
    )
    assert "你已知的事" in text
    assert "为老爷工作 30 年" in text
    assert "识字但不识洋文" in text


def test_knowledge_section_omitted_when_empty():
    text = build_npc_system(**_base_kwargs(knowledge=[]))
    assert "你已知的事" not in text


def test_scene_context_renders_time_and_location_and_peers():
    scene = {
        "current_time": "第3天·上午",
        "my_location": "茶摊",
        "player_location": "茶摊",
        "peer_npcs": [
            {"name": "赵姐", "personality": "热心，爱八卦"},
            {"name": "李掌柜", "personality": ""},
        ],
    }
    text = build_npc_system(**_base_kwargs(scene_context=scene))
    assert "## 当前场景" in text
    assert "第3天·上午" in text
    assert "你目前在：茶摊" in text
    # Same location → no separate "玩家此刻在" line
    assert "玩家此刻在" not in text
    assert "赵姐（热心，爱八卦）" in text
    assert "李掌柜" in text  # personality empty → bare name


def test_scene_context_emits_player_location_when_different():
    scene = {
        "current_time": "第3天·上午",
        "my_location": "诊所",
        "player_location": "茶摊",
        "peer_npcs": [],
    }
    text = build_npc_system(**_base_kwargs(scene_context=scene))
    assert "你目前在：诊所" in text
    assert "玩家此刻在：茶摊" in text


def test_scene_context_section_omitted_when_no_meaningful_fields():
    scene = {"current_time": "", "my_location": "", "player_location": "", "peer_npcs": []}
    text = build_npc_system(**_base_kwargs(scene_context=scene))
    assert "## 当前场景" not in text


def test_current_intent_renders_goal_urgency_stage():
    intent = {
        "current_goal": "把玩家试探出来",
        "urgency": 7,
        "plan_stage": 1,
        "plan_stages": ["观望", "准备", "行动"],
        "blocked_by": None,
    }
    text = build_npc_system(**_base_kwargs(current_intent=intent))
    assert "## 你心里在意的事" in text
    assert "把玩家试探出来" in text
    assert "7/10" in text
    assert "「准备」" in text
    assert "挡住" not in text  # no blocker


def test_current_intent_renders_blocked_by_when_present():
    intent = {
        "current_goal": "走出茶摊",
        "urgency": 5,
        "plan_stage": 0,
        "plan_stages": ["观望"],
        "blocked_by": "玩家拦着",
    }
    text = build_npc_system(**_base_kwargs(current_intent=intent))
    assert "「玩家拦着」" in text
    assert "挡住" in text


def test_current_intent_section_omitted_when_no_goal():
    text = build_npc_system(**_base_kwargs(current_intent={"current_goal": "", "urgency": 5}))
    assert "## 你心里在意的事" not in text


def test_full_assembly_keeps_stable_prefix_before_variable_suffix():
    """world/knowledge/secret/reflection/行为规则 sit BEFORE scene/intent/voice/memories/trust."""
    text = build_npc_system(
        **_base_kwargs(
            world_setting="WORLD_TOKEN",
            knowledge=["KNOWLEDGE_TOKEN"],
            npc_secret="SECRET_TOKEN",
            reflection="REFLECTION_TOKEN",
            scene_context={"current_time": "T", "my_location": "L", "peer_npcs": []},
            current_intent={"current_goal": "INTENT_TOKEN", "urgency": 5, "plan_stage": 0, "plan_stages": []},
            voice_anchor=["VOICE_TOKEN"],
            memories=[{"round_number": 1, "content": "MEMORY_TOKEN"}],
            trust=5,
            mood="紧张",
        )
    )
    pos = {token: text.index(token) for token in [
        "WORLD_TOKEN", "KNOWLEDGE_TOKEN", "SECRET_TOKEN", "REFLECTION_TOKEN",
        "行为规则",
        "INTENT_TOKEN", "VOICE_TOKEN", "MEMORY_TOKEN",
    ]}
    # Stable prefix block (everything up to and including "行为规则")…
    for stable in ("WORLD_TOKEN", "KNOWLEDGE_TOKEN", "SECRET_TOKEN", "REFLECTION_TOKEN"):
        assert pos[stable] < pos["行为规则"], f"{stable} should be before 行为规则"
    # …precedes the variable suffix block.
    for variable in ("INTENT_TOKEN", "VOICE_TOKEN", "MEMORY_TOKEN"):
        assert pos["行为规则"] < pos[variable], f"{variable} should be after 行为规则"
