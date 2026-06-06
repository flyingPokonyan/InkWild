"""Phase 1.A.3 — assert Director/NPC system prompts have a cache-friendly stable prefix.

The first N bytes of the system prompt MUST be identical across turns of the
same world (varying only memory_context / per-turn instruction / mood / trust /
memories). This is what lets DeepSeek's auto prefix-cache (and Anthropic's
explicit cache_control in 1.A.4) hit on the bulk of the prompt.
"""
from __future__ import annotations

import hashlib

from engine.prompts import build_director_system, build_npc_system

# Must comfortably exceed the longest fixed (world setting + behavior rules)
# block. Anything shorter would be a regression.
_PREFIX_BYTES = 800


def _prefix_hash(text: str, n: int = _PREFIX_BYTES) -> str:
    return hashlib.sha256(text.encode("utf-8")[:n]).hexdigest()


def _director_kwargs(memory: str = "") -> dict:
    return dict(
        base_setting="雾隐镇是一个民国小镇，雾气常年不散。" * 3,
        script_setting="凶手是管家王福。",
        npc_descriptions="王福：忠厚寡言。\n赵姐：热心。" * 4,
        ending_conditions="当玩家指认凶手时触发完美结局。",
        game_mode="script",
        memory_context=memory,
        script_type="mystery",
    )


def test_director_prefix_stable_across_changing_memory_context():
    a = build_director_system(**_director_kwargs(memory="第3轮：玩家见过王福。"))
    b = build_director_system(**_director_kwargs(memory="第8轮：玩家在卧室发现血迹。"))
    c = build_director_system(**_director_kwargs(memory=""))

    assert _prefix_hash(a) == _prefix_hash(b) == _prefix_hash(c)
    assert "重要记忆" in a  # variable suffix is still present
    assert "重要记忆" not in c  # not added when empty


def test_director_memory_context_appears_at_end():
    s = build_director_system(**_director_kwargs(memory="MEMORY_MARKER_XYZ"))
    # MEMORY_MARKER must be in the last 25% of the prompt — i.e. the variable suffix.
    marker_index = s.index("MEMORY_MARKER_XYZ")
    assert marker_index > len(s) * 0.75, (
        f"memory_context should be in the variable suffix, but appears at "
        f"position {marker_index} of {len(s)} (only {marker_index/len(s):.0%} in)"
    )


def _npc_kwargs(*, instruction: str, trust: int, mood: str, memories: list | None) -> dict:
    return dict(
        npc_name="王福",
        npc_personality="忠厚寡言，做事一丝不苟。" * 3,
        npc_secret="他知道老爷的遗嘱内容。" * 2,
        instruction=instruction,
        memories=memories,
        trust=trust,
        mood=mood,
    )


_NPC_PREFIX_END_MARKER = "## 行为规则"  # last block of NPC stable prefix


def _npc_stable_prefix(text: str) -> str:
    """Slice the NPC system prompt up to and including the behavior-rules block,
    which is the boundary between stable prefix and per-turn variable suffix.
    """
    idx = text.index(_NPC_PREFIX_END_MARKER)
    end_of_block = text.find("\n\n", idx)
    if end_of_block == -1:
        end_of_block = len(text)
    return text[:end_of_block]


def test_npc_prefix_stable_across_changing_instruction_trust_mood_memories():
    a = build_npc_system(**_npc_kwargs(
        instruction="试探玩家是否知道遗嘱",
        trust=3,
        mood="正常",
        memories=None,
    ))
    b = build_npc_system(**_npc_kwargs(
        instruction="向玩家透露老爷昨夜的异常",
        trust=7,
        mood="紧张",
        memories=[{"round_number": 5, "content": "玩家追问遗嘱"}],
    ))
    assert _npc_stable_prefix(a) == _npc_stable_prefix(b)


def test_npc_per_turn_fields_in_variable_suffix():
    s = build_npc_system(**_npc_kwargs(
        instruction="UNIQUE_INSTRUCTION_TOKEN",
        trust=9,
        mood="愤怒",
        memories=[{"round_number": 1, "content": "MEM_TOKEN"}],
    ))
    for token in ("UNIQUE_INSTRUCTION_TOKEN", "MEM_TOKEN", "信任度：9", "愤怒"):
        assert token in s
        assert s.index(token) > len(s) * 0.5, (
            f"per-turn token {token!r} should be in the variable suffix"
        )
