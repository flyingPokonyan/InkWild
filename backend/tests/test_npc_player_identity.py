"""NPC awareness of WHO the player is.

The player picks a rich playable character at session start, but until now
the NPC was never told the player's public identity — it only saw a trust
number. These tests pin the "你面对的人是谁" block that injects the player
character's public identity (name + description) into the NPC prompt's
cache-friendly stable prefix. Inner persona (personality/secret) is NOT fed —
the engine never puppets the player.
"""
from __future__ import annotations

from engine.prompts import build_npc_system, build_npc_system_v2

_PLAYER = {
    "name": "甄嬛",
    "description": "新晋妃嫔，身份惹眼，宫人对你既奉承又提防。",
}


def test_v2_player_identity_appears_in_stable_prefix():
    text = build_npc_system_v2("皇后", "端庄狠辣", None, player_identity=_PLAYER)
    assert "你面对的人是谁" in text
    assert "甄嬛" in text
    assert "新晋妃嫔" in text
    # Stable prefix: must sit before the per-turn / static action vocabulary
    # so the provider prefix cache still covers it (player identity is constant
    # within a session).
    assert text.index("甄嬛") < text.index("你这一轮可以做什么")


def test_v2_player_identity_omitted_when_absent():
    text = build_npc_system_v2("皇后", "端庄狠辣", None)
    assert "你面对的人是谁" not in text


def test_v2_disambiguates_second_person_in_description():
    # The playable description is authored in mixed voice ("...对你...") where
    # "你" means the player. Inside the NPC prompt "你" = the NPC, so the block
    # must tell the NPC that "你" in the description refers to the player.
    text = build_npc_system_v2("皇后", "端庄狠辣", None, player_identity=_PLAYER)
    assert "甄嬛" in text
    assert "不要替" in text  # do-not-puppet guardrail present


def test_v1_player_identity_appears_in_stable_prefix():
    text = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚寡言",
        npc_secret=None,
        instruction="回应玩家",
        player_identity=_PLAYER,
    )
    assert "你面对的人是谁" in text
    assert "甄嬛" in text
    assert text.index("甄嬛") < text.index("行为规则")


def test_v1_player_identity_omitted_when_absent():
    text = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚寡言",
        npc_secret=None,
        instruction="回应玩家",
    )
    assert "你面对的人是谁" not in text
