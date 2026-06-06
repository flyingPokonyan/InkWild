"""Tests for ``services.cover_brief`` — V3 unified template (2026-05-19).

These tests assert prompt **structure** (key fragments present), not literal
character-for-character equality, so the prompts can evolve as the spec is
tuned without thrashing tests.
"""
from __future__ import annotations

import pytest

from schemas.ip_knowledge_pack import IPCharacter, IPKnowledgePack
from services.cover_brief import (
    CharacterCoverBrief,
    CoverBrief,
    EndingCoverBrief,
    build_character_portrait_prompt,
    build_ending_card_prompt,
    build_script_cover_prompt,
    build_world_cover_prompt,
    build_world_hero_prompt,
    derive_character_reference_anchor,
)


# ---------------------------------------------------------------------------
# Schema construction
# ---------------------------------------------------------------------------


def test_cover_brief_minimal():
    """Schema accepts the V3 minimal field set (no ip_mode, no typography_hint)."""
    b = CoverBrief(
        world_name="逐玉",
        world_name_english="Pursuit of Jade",
        genre_tag="古装权谋",
        mood="毛笔书法、朱印、墨色",
        ip_name="逐玉",
    )
    assert b.ip_name == b.world_name
    assert "朱印" in b.mood


def test_cover_brief_all_defaults():
    """Only world_name is required."""
    b = CoverBrief(world_name="无名世界")
    assert b.ip_name is None
    assert b.mood == ""
    assert b.world_name_english == ""


def test_character_cover_brief_with_ref():
    c = CharacterCoverBrief(
        name="谢征",
        name_english="Xie Zheng",
        reference_anchor="《逐玉》里的武安侯",
        mood_anchor="隐忍深沉",
    )
    assert c.reference_anchor is not None
    assert c.gender == ""  # fallback fields unused when ref is present


def test_character_cover_brief_4dim_fallback():
    c = CharacterCoverBrief(
        name="李婉",
        name_english="Li Wan",
        gender="女",
        age_band="少女",
        role_class="药铺女儿",
        mood_anchor="惊魂未定",
    )
    assert c.reference_anchor is None
    assert c.gender == "女"


# ---------------------------------------------------------------------------
# derive_character_reference_anchor (unchanged from pre-V3)
# ---------------------------------------------------------------------------


def _ip_pack_with(chars: list[IPCharacter]) -> IPKnowledgePack:
    return IPKnowledgePack(
        ip_name="逐玉",
        ip_type="tv",
        fidelity_mode="strict",
        summary="...",
        characters=chars,
        places=[],
        factions=[],
        iconic_objects=[],
        key_events=[],
        tone_lingo=[],
        passages=[],
    )


def test_character_reference_anchor_from_ip_pack():
    pack = _ip_pack_with([
        IPCharacter(
            name="谢征",
            role_in_story="男主",
            relation_to_protagonist="本人",
            traits=["武安侯"],
            must_have=True,
        ),
    ])
    anchor = derive_character_reference_anchor(
        character_name="谢征", ip_name="逐玉", ip_pack=pack
    )
    assert anchor == "《逐玉》里的男主"


def test_character_reference_anchor_no_pack():
    assert (
        derive_character_reference_anchor(character_name="李婉", ip_name="逐玉", ip_pack=None)
        is None
    )


def test_character_reference_anchor_no_ip_name():
    pack = _ip_pack_with([])
    assert (
        derive_character_reference_anchor(character_name="李婉", ip_name=None, ip_pack=pack)
        is None
    )


def test_character_reference_anchor_not_in_pack():
    """Admin-added supporting characters fall through to 4-dim fallback."""
    pack = _ip_pack_with([
        IPCharacter(
            name="谢征",
            role_in_story="男主",
            relation_to_protagonist="本人",
            traits=[],
            must_have=True,
        ),
    ])
    anchor = derive_character_reference_anchor(
        character_name="王二", ip_name="逐玉", ip_pack=pack
    )
    assert anchor is None


def test_character_reference_anchor_empty_role_uses_name():
    pack = _ip_pack_with([
        IPCharacter(
            name="谢征",
            role_in_story="",
            relation_to_protagonist="本人",
            traits=[],
            must_have=True,
        ),
    ])
    anchor = derive_character_reference_anchor(
        character_name="谢征", ip_name="逐玉", ip_pack=pack
    )
    assert anchor == "《逐玉》里的谢征"


# ---------------------------------------------------------------------------
# Prompt builders — V3 unified template
# ---------------------------------------------------------------------------


def _brief(
    world_name: str = "逐玉",
    ip_name: str | None = "逐玉",
    genre_tag: str = "古装权谋",
    mood: str = "毛笔书法、朱印、墨色",
) -> CoverBrief:
    return CoverBrief(
        world_name=world_name,
        world_name_english="Pursuit of Jade",
        genre_tag=genre_tag,
        mood=mood,
        ip_name=ip_name,
    )


# --- Hero ---


def test_world_hero_known_ip_exact_no_self_reference():
    """When ip_name == world_name we drop the awkward 「视觉对标《X》」 self-loop."""
    p = build_world_hero_prompt(_brief(world_name="三体", ip_name="三体", genre_tag="硬科幻"))
    assert "《三体》" in p
    assert "硬科幻" in p
    assert "视觉对标" not in p  # no self-reference
    assert "key art" in p
    assert "不要 logo" in p


def test_world_hero_hybrid_lifts_ip_anchor_to_subject():
    """When ip_name != world_name, IP anchor appears in the first-clause subject."""
    p = build_world_hero_prompt(
        _brief(world_name="凡尘仙途", ip_name="诛仙", genre_tag="仙侠")
    )
    # The IP anchor is in the opening subject clause
    assert p.startswith("《凡尘仙途》—— 一部仙侠作品，视觉对标《诛仙》。")
    assert "key art" in p


def test_world_hero_original_no_ip_clause():
    """ip_name=None drops the visual reference but keeps the rest."""
    p = build_world_hero_prompt(_brief(world_name="无人记得的冬", ip_name=None))
    assert "《无人记得的冬》" in p
    assert "视觉对标" not in p
    assert "key art" in p


def test_world_hero_includes_mood_clause():
    p = build_world_hero_prompt(_brief(mood="毛笔书法、朱印、龙袍"))
    assert "画面气质：毛笔书法、朱印、龙袍" in p
    assert "不必强制做成标题字" in p  # mood ablation safety hint


def test_world_hero_empty_mood_drops_clause():
    """Mood ablation: empty mood produces no clause (loud failure, not silent fallback)."""
    p = build_world_hero_prompt(_brief(mood=""))
    assert "画面气质" not in p


def test_world_hero_title_hint_with_english():
    p = build_world_hero_prompt(_brief())
    assert "「逐玉」" in p
    assert "Pursuit of Jade" in p


def test_world_hero_title_hint_drops_english_when_empty():
    brief = CoverBrief(
        world_name="逐玉", world_name_english="", mood="墨色", ip_name="逐玉",
    )
    p = build_world_hero_prompt(brief)
    assert "「逐玉」" in p
    # No trailing " / <english>"
    assert " / " not in p


# --- World cover (3:2, independent generation, used by list cards) ---


def test_world_cover_basic_structure():
    """3:2 cover prompt mirrors hero's subject + mood + negatives,
    but adds list-card usage context and omits title_hint."""
    p = build_world_cover_prompt(_brief(world_name="凡尘仙途", ip_name="诛仙", genre_tag="仙侠"))
    assert "《凡尘仙途》" in p
    assert "视觉对标《诛仙》" in p
    assert "3:2" in p
    assert "列表" in p  # usage context for the model to reason about composition
    assert "不要 logo" in p


def test_world_cover_no_title_hint():
    """Cover must NOT include the title_hint clause: list cards render the
    world name in system font next to the image, so a painted title would
    collide with UI metadata. Model is left to infer from the usage hint."""
    p = build_world_cover_prompt(_brief())
    assert "若画面包含标题文字" not in p
    assert "「逐玉」" not in p
    assert "Pursuit of Jade" not in p


def test_world_cover_includes_mood():
    p = build_world_cover_prompt(_brief(mood="毛笔书法、朱印"))
    assert "画面气质：毛笔书法、朱印" in p


def test_world_cover_no_self_reference():
    """When ip_name == world_name we drop the 视觉对标 self-loop (same rule as hero)."""
    p = build_world_cover_prompt(_brief(world_name="三体", ip_name="三体"))
    assert "视觉对标" not in p


# --- Script cover ---


def test_script_cover_prompt():
    p = build_script_cover_prompt(
        _brief(),
        script_title="锦州血案",
        script_title_english="Jinzhou Massacre",
    )
    assert "《逐玉》中的剧情线《锦州血案》" in p
    assert "key art" in p
    assert "3:2" in p
    assert "「锦州血案」" in p
    assert "Jinzhou Massacre" in p


def test_script_cover_includes_world_mood():
    p = build_script_cover_prompt(
        _brief(mood="毛笔书法、朱印"),
        script_title="锦州血案",
        script_title_english="Jinzhou Massacre",
    )
    assert "画面气质：毛笔书法、朱印" in p


# --- Character portrait ---


def test_character_portrait_with_ref_anchor_ip_anchored_world():
    char = CharacterCoverBrief(
        name="谢征",
        name_english="Xie Zheng",
        reference_anchor="《逐玉》里的武安侯",
        mood_anchor="隐忍深沉",
    )
    p = build_character_portrait_prompt(_brief(), char)
    assert "「谢征」" in p
    assert "《逐玉》里的武安侯" in p
    assert "隐忍深沉" in p
    # Style cue surfaces because the world has an ip_name
    assert "《逐玉》风格的" in p
    assert "眼线落在画面上三分位附近" in p
    assert "画面中不要出现任何文字" in p
    assert "2:3" in p


def test_character_portrait_4dim_fallback_original_world():
    """Original worlds (ip_name=None) drop the awkward 「《X》风格的」 self-reference."""
    char = CharacterCoverBrief(
        name="李婉",
        name_english="Li Wan",
        gender="女",
        age_band="少女",
        role_class="药铺女儿",
        mood_anchor="惊魂未定",
    )
    brief = _brief(world_name="无人记得的冬", ip_name=None)
    p = build_character_portrait_prompt(brief, char)
    assert "女性" in p
    assert "少女" in p
    assert "药铺女儿" in p
    assert "惊魂未定" in p
    assert "《无人记得的冬》风格的" not in p
    assert "「李婉」" in p


def test_character_portrait_descriptor_with_ref_no_mood():
    char = CharacterCoverBrief(
        name="谢征",
        name_english="Xie Zheng",
        reference_anchor="《逐玉》里的武安侯",
        mood_anchor="",
    )
    p = build_character_portrait_prompt(_brief(), char)
    # No trailing "；" when mood is empty
    assert "《逐玉》里的武安侯）" in p
    assert "《逐玉》里的武安侯；）" not in p


# --- Ending card ---


def test_ending_card_prompt():
    ending = EndingCoverBrief(
        title="真相大白",
        title_english="The Truth Revealed",
        description="二十年悬案水落石出，老人独坐黄昏玉米地远眺绿皮火车。",
    )
    p = build_ending_card_prompt(_brief(), ending)
    assert "为《逐玉》创作一张「真相大白」结局画面卡" in p
    assert "故事到这里的状态：二十年悬案水落石出" in p
    assert "「真相大白」" in p
    assert "无血腥暴力直白展示" in p
    assert "3:2" in p


def test_ending_card_includes_world_mood():
    ending = EndingCoverBrief(
        title="真相大白", title_english="", description="...",
    )
    p = build_ending_card_prompt(_brief(mood="毛笔书法、朱印"), ending)
    assert "画面气质：毛笔书法、朱印" in p


def test_ending_card_title_is_chinese_only_by_design():
    """Ending cards keep dramatic Chinese title — no bilingual subtitle."""
    ending = EndingCoverBrief(
        title="家国并肩", title_english="Side by Side", description="...",
    )
    p = build_ending_card_prompt(_brief(), ending)
    assert "「家国并肩」" in p
    assert "Side by Side" not in p


# --- Cross-cutting invariants ---


@pytest.mark.parametrize(
    "world_name,ip_name",
    [
        ("三体", "三体"),         # known IP equals world name
        ("凡尘仙途", "诛仙"),     # hybrid
        ("无人记得的冬", None),    # original
    ],
)
def test_all_world_level_prompts_enforce_logo_safety(world_name, ip_name):
    """Logo / brand negative must be in every prompt — hard product rule.

    The face-likeness restriction was dropped 2026-05-20 (non-commercial use);
    only logo / brand / award / broadcaster signage is still suppressed.
    """
    brief = _brief(world_name=world_name, ip_name=ip_name)
    char = (
        CharacterCoverBrief(
            name="谢征", name_english="Xie Zheng",
            reference_anchor=f"《{ip_name}》里的男主",
        )
        if ip_name
        else CharacterCoverBrief(
            name="李婉", name_english="Li Wan",
            gender="女", age_band="少女", role_class="药铺女儿",
        )
    )
    ending = EndingCoverBrief(title="结局", title_english="Ending", description="...")
    for p in (
        build_world_hero_prompt(brief),
        build_script_cover_prompt(brief, script_title="t", script_title_english="T"),
        build_character_portrait_prompt(brief, char),
        build_ending_card_prompt(brief, ending),
    ):
        assert "不要 logo" in p
        assert "真实演员" not in p  # face-likeness restriction lifted


def test_prompts_stay_under_500_chars():
    """Sanity: V3 prompts are ~150-250 chars; reject regression to dense pipelines (~1100+)."""
    brief = _brief()
    char = CharacterCoverBrief(
        name="谢征", name_english="Xie Zheng",
        reference_anchor="《逐玉》里的武安侯，化名言正", mood_anchor="隐忍深沉",
    )
    ending = EndingCoverBrief(
        title="家国并肩", title_english="Side by Side",
        description="假婚演成真情，男女主登城眺望远方。",
    )
    assert len(build_world_hero_prompt(brief)) < 500
    assert len(build_script_cover_prompt(brief, script_title="锦州血案", script_title_english="Jinzhou Massacre")) < 500
    assert len(build_character_portrait_prompt(brief, char)) < 500
    assert len(build_ending_card_prompt(brief, ending)) < 500
