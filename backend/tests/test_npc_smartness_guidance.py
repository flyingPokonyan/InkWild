"""Regression-guard for the NPC-1 智能性引导.

The "smartness" of multi-NPC scenes lives in two paragraphs of prompt text:
- Director prompt §「谁开口、按什么顺序」teaches Director that
  involved_npcs ≠ npc_speech_order and shows few-shot examples of selective
  speaking.
- NPC behavior rules teach the NPC that 沉默 is a legal choice and that
  礼貌接龙 is forbidden.

These are pure prompt strings — easy to silently delete during a refactor and
the failure mode is "NPCs feel a bit dumb again", which won't surface in any
behavioral test. This file pins the key phrases so deletion fails CI loudly.
"""
from __future__ import annotations

from engine.prompts import build_director_system, build_npc_system


# === Director prompt anchors ===

def _director_prompt() -> str:
    return build_director_system(
        base_setting="一个民国小镇。",
        script_setting="",
        npc_descriptions="王福：忠厚。",
        ending_conditions="",
        game_mode="script",
    )


def test_director_prompt_anchors_speech_order_section():
    prompt = _director_prompt()
    # The section header itself.
    assert "谁开口、按什么顺序" in prompt, (
        "Director system prompt 缺失 npc_speech_order 引导段。"
        "这段是 NPC-1 智能性的核心，不能被删。"
    )


def test_director_prompt_distinguishes_involved_from_speech_order():
    """Director must be told the two lists aren't the same thing."""
    prompt = _director_prompt()
    assert "involved_npcs" in prompt and "npc_speech_order" in prompt
    # The exact rule.
    assert "不一定相等" in prompt, (
        "Director prompt 必须明确 involved_npcs 跟 npc_speech_order 不一定相等，"
        "否则 LLM 会默认全员发言。"
    )


def test_director_prompt_anchors_smaller_default():
    """Director must be biased toward 1-2 speakers, not 'cap=3 every turn'."""
    prompt = _director_prompt()
    assert "1-2 个发言者" in prompt or "1-2 人" in prompt or "1-2 个开口" in prompt, (
        "Director prompt 必须默认偏好 1-2 个发言者。"
    )


def test_director_prompt_carries_few_shot_examples():
    """Abstract rules without concrete examples don't change LLM behavior.
    All four canonical scenarios must stay in the prompt."""
    prompt = _director_prompt()
    # Section header for the examples block.
    assert "用法示例" in prompt, "Director prompt 缺失 speech_order few-shot 段"
    # Each canonical scenario.
    for marker in ("单人对话", "双人张力", "群戏议事", "旁观沉默"):
        assert marker in prompt, (
            f"Director prompt 缺失 few-shot 示例「{marker}」。"
            "few-shot 是抽象规则真正落地的关键，不能少。"
        )


def test_director_prompt_explains_silent_witness_pattern():
    """The 'put NPC in involved_npcs but not in speech_order' pattern must be
    explicit — it's the lever Director uses to keep NPCs on stage as silent
    witnesses without forcing them to speak."""
    prompt = _director_prompt()
    assert "在场但沉默" in prompt or "在场观察" in prompt, (
        "Director prompt 必须明确「在场但沉默」的用法，否则 Director 不知道这是个选项。"
    )


# === NPC prompt anchors ===

def _npc_prompt() -> str:
    return build_npc_system(
        npc_name="王福",
        npc_personality="忠厚",
        npc_secret=None,
        instruction=".",
    )


def test_npc_prompt_anchors_silence_as_legal_choice():
    """The single most important guardrail against 'every NPC must say
    something' — this phrase is what gives the LLM permission to be quiet."""
    prompt = _npc_prompt()
    assert "沉默是合法选择" in prompt, (
        "NPC prompt 必须明确「沉默是合法选择」。这是防止 LLM 硬挤台词的核心引导。"
    )


def test_npc_prompt_anchors_no_polite_relay():
    """NPC must be told that politely responding to every mentioned topic is
    NOT what their character would do. Without this, multi-NPC turns degrade
    into round-robin chatter."""
    prompt = _npc_prompt()
    assert "礼貌地回应每一个" in prompt, (
        "NPC prompt 必须明确禁止「礼貌接龙」式回应，否则多 NPC 接话会变刷屏。"
    )


def test_npc_prompt_offers_action_only_or_empty_output():
    """The LLM needs explicit format permission to output just an action or
    nothing at all — 'be silent' alone isn't enough; it needs to know how."""
    prompt = _npc_prompt()
    # Mention of action-only output.
    assert "动作描写" in prompt
    # Mention of empty-string output.
    assert "空字符串" in prompt, (
        "NPC prompt 必须告诉 LLM 可以输出空字符串保持沉默，"
        "不告诉它具体怎么做，「沉默是合法选择」就是空话。"
    )


def test_npc_prompt_explains_peer_dialogue_listening():
    """When peers speak first, NPC must know it must react like it actually
    heard them — that's what makes sequential dialogue feel alive."""
    prompt = _npc_prompt()
    assert "本轮已有人发言" in prompt, (
        "NPC prompt 必须明确「本轮已有人发言时如何反应」，"
        "这是 NPC-1 顺序对话的接话规则。"
    )
