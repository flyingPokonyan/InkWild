"""Tests for ``services.cover_brief`` — V4 画法体系 (2026-06-26 rewrite).

Covers: 画法池, genre→hash style spread, art_style/cover_focus injection,
the five prompt builders, craft discipline (anti-厚涂, no border), IP fidelity,
and the hero full-bleed rule.
"""
from services.cover_brief import (
    ART_STYLE_FALLBACK,
    GENRE_STYLE_POOL,
    STYLE_DESC,
    CharacterCoverBrief,
    CoverBrief,
    EndingCoverBrief,
    build_character_portrait_prompt,
    build_ending_card_prompt,
    build_script_cover_prompt,
    build_world_cover_prompt,
    build_world_hero_prompt,
    derive_character_reference_anchor,
    pick_art_style,
    resolve_style_desc,
)


def _brief(**kw) -> CoverBrief:
    d = dict(world_name="雾隐镇", essence="一个常年被浓雾笼罩的小镇", art_style="水墨写意")
    d.update(kw)
    return CoverBrief(**d)


# --- 画法池 STYLE_DESC ---


def test_style_pool_has_strong_styles():
    assert len(STYLE_DESC) >= 10
    for k in ("水墨写意", "工笔重彩", "铜版木刻", "水彩淡彩", "丝网波普"):
        assert k in STYLE_DESC


def test_style_pool_has_no_thick_paint_baseline():
    """The whole point of V4: no 厚涂/概念美术/photoreal in the 画法池."""
    for name, desc in STYLE_DESC.items():
        assert "厚涂" not in name and "厚涂" not in desc
        assert "概念美术" not in name
        assert "写实渲染" not in desc


def test_genre_pools_reference_only_valid_styles():
    for cat, pool in GENRE_STYLE_POOL.items():
        assert pool, f"{cat} pool empty"
        for s in pool:
            assert s in STYLE_DESC, f"{cat} -> {s} not in STYLE_DESC"


# --- pick_art_style: genre→hash spread ---


def test_pick_is_deterministic():
    assert pick_art_style("古风宫廷", "甄嬛传") == pick_art_style("古风宫廷", "甄嬛传")


def test_pick_in_genre_pool():
    for name in ("长安", "大唐狄公案", "梦华录"):
        assert pick_art_style("古风宫廷", name) in GENRE_STYLE_POOL["古风宫廷"]


def test_pick_spreads_same_genre():
    """Same-genre worlds must NOT all collapse onto one style (the bug we fixed)."""
    names = ["长安十二时辰", "大唐狄公案", "梦华录", "庆余年", "后宫·甄嬛传"]
    styles = {pick_art_style("古风宫廷", n) for n in names}
    assert len(styles) >= 2


def test_pick_unknown_category_uses_other_pool():
    assert pick_art_style("不存在的大类", "某世界") in GENRE_STYLE_POOL["其他"]
    assert pick_art_style("", "某世界") in GENRE_STYLE_POOL["其他"]


# --- resolve_style_desc fallback ---


def test_resolve_known_style():
    assert resolve_style_desc("丝网波普") == STYLE_DESC["丝网波普"]


def test_resolve_empty_and_unknown_fallback():
    fb = STYLE_DESC[ART_STYLE_FALLBACK]
    assert resolve_style_desc("") == fb
    assert resolve_style_desc("不存在画法") == fb


# --- art_style injection ---


def test_art_style_desc_injected():
    p = build_world_cover_prompt(_brief(art_style="丝网波普"))
    assert STYLE_DESC["丝网波普"] in p


def test_art_style_empty_falls_back_in_prompt():
    p = build_world_cover_prompt(_brief(art_style=""))
    assert STYLE_DESC[ART_STYLE_FALLBACK] in p


# --- cover_focus injection (主题钩子, not 摆拍) ---


def test_cover_focus_injected_as_theme():
    p = build_world_cover_prompt(_brief(cover_focus="雾里失踪之谜"))
    assert "雾里失踪之谜" in p
    assert "这张封面要传达" in p
    assert "由你构想" in p  # leaves composition to gpt-image


def test_cover_focus_empty_no_clause():
    p = build_world_cover_prompt(_brief(cover_focus=""))
    assert "这张封面要传达" not in p


# --- craft discipline (anti-厚涂, 媒介=画, no border) ---


def test_craft_discipline_present():
    p = build_world_cover_prompt(_brief())
    assert "媒介始终是「画」" in p
    assert "写实厚涂渲染" in p  # explicitly avoided


def test_no_border_in_all_builders():
    """No decorative inner border anywhere — full bleed for all image types."""
    for builder in (
        lambda: build_world_hero_prompt(_brief()),
        lambda: build_world_cover_prompt(_brief()),
        lambda: build_script_cover_prompt(_brief(), script_title="X", script_title_english=""),
        lambda: build_ending_card_prompt(_brief(), EndingCoverBrief(title="T", description="D")),
    ):
        p = builder()
        assert "不要任何内嵌画框" in p


# --- builders: ratios + logo ---


def test_world_cover_basics():
    p = build_world_cover_prompt(_brief())
    assert "3:2" in p
    assert "不要任何可读文字" in p


def test_world_hero_basics():
    p = build_world_hero_prompt(_brief(art_style="新艺术装饰"))
    assert "21:9" in p
    assert "全屏沉浸" in p


def test_script_cover_uses_world_style():
    p = build_script_cover_prompt(
        _brief(art_style="铜版木刻"), script_title="锦州血案", script_title_english="",
        script_essence="一桩旧案")
    assert "锦州血案" in p
    assert STYLE_DESC["铜版木刻"] in p
    assert "3:2" in p


def test_portrait_keeps_clear_face():
    char = CharacterCoverBrief(name="谢征", gender="男", age_band="青年", role_class="武将")
    p = build_character_portrait_prompt(_brief(art_style="工笔重彩"), char)
    assert "谢征" in p
    assert "清晰可辨的面部" in p
    assert STYLE_DESC["工笔重彩"] in p
    assert "2:3" in p


def test_ending_card_basics():
    ending = EndingCoverBrief(title="家国并肩", description="男女主登城眺望远方。")
    p = build_ending_card_prompt(_brief(), ending)
    assert "家国并肩" in p
    assert "无血腥暴力直白展示" in p
    assert "3:2" in p


# --- IP fidelity ---


def test_ip_world_fidelity_translates():
    p = build_world_cover_prompt(_brief(world_name="逐玉", ip_name="逐玉", essence=""))
    assert "原作/已知 IP 识别优先" in p
    assert "用上述画法转译" in p


def test_original_world_fidelity():
    p = build_world_cover_prompt(_brief(ip_name=None))
    assert "忠实这个世界的内核" in p


def test_ip_fallback_softens_anchor():
    p = build_world_cover_prompt(_brief(world_name="凡尘仙途", ip_name="诛仙"), ip_fallback=True)
    assert "视觉对标《诛仙》" in p


# --- char ref anchor (unchanged helper) ---


def test_ref_anchor_none_without_ip():
    assert derive_character_reference_anchor(character_name="甲", ip_name=None, ip_pack=None) is None
    assert derive_character_reference_anchor(character_name="甲", ip_name="某IP", ip_pack=None) is None
