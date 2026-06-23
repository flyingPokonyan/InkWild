"""Cover image brief — drives all cover/hero/script/portrait/ending prompts.

V3 simplified (2026-05-19). Earlier hybrid/known_ip_exact/original branching
was collapsed into a single template: the IP name is lifted to the first
clause subject and an LLM-derived ``mood`` cue replaces the static
typography-hint table. The 16-image IP-anchor experiment + the 4-image mood
ablation (see ``backend/scripts/exp_cover_prompts_*.py``) showed:

1. Putting "电影海报" in the prompt pushes the model to the商业海报 mean —
   we now ask for "key art" with explicit format flexibility (海报/剧照/
   宣传画/概念图) so the model can break out of the poster template.
2. Without a ``mood`` cue the model collapses back to the商业海报 mean even
   with IP anchor lifted. The mood cue is the hook that lets the model
   try non-poster forms (水墨长卷、工笔群像、戏剧绘画).
3. Mood is LLM-derived per world (in ``cover_brief_helper``) — a static
   genre→mood lookup table reintroduces "all 古装 worlds collide on
   毛笔书法+朱印", which is exactly the均值 we want to avoid.

The whole brief is reconstructed on-the-fly each generation run; nothing
is persisted (``worlds.visual_brief`` / ``scripts.visual_brief`` were
dropped in migration ``9a8b7c6d5e4f``).

See ``docs/plans/world-detail-and-cover-v3-2026-05.md`` for the full spec.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from schemas.ip_knowledge_pack import IPKnowledgePack


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CoverBrief(BaseModel):
    """World-level brief. One per world; drives hero/cover, script cover,
    ending card, and (combined with CharacterCoverBrief) character portrait
    prompts.

    All fields are derivable from a ``World`` row + (optional) IPRecognition.
    ``world_name_english`` and ``mood`` are filled by ``cover_brief_helper``
    in a single LLM call; the rest is mechanical.
    """

    world_name: str
    world_name_english: str = ""
    genre_tag: str = ""  # short era+genre phrase, e.g. "古装权谋" / "民国谍战"
    # 3-5 个画面气质 cue 词（顿号分隔）— LLM 派生，避免静态映射表的"同题材撞均值"。
    # mood ablation (V3_UNIFIED): 没有这一项时模型回到商业海报均值。
    mood: str = ""
    # Reference IP name when the world borrows visual DNA from a known title
    # (e.g. world_name="凡尘仙途", ip_name="诛仙"). Equal to world_name when
    # the world IS the IP. None when original / IP recognizer didn't fire.
    ip_name: str | None = None
    # World essence (= the world's description). For ORIGINAL worlds this is the
    # model's only window into what the world is about, so it's injected into the
    # hero/cover prompt verbatim — without it the model degrades to "draw the
    # environment + title". For IP worlds it's ignored: the IP name is a far
    # richer anchor than any description and the model already knows the canon.
    essence: str = ""


class CharacterCoverBrief(BaseModel):
    """Character-level brief for portrait generation. One per character.

    ``reference_anchor`` is the strong signal for known-IP characters and,
    when set, supersedes the 4-dim fallback. The 4-dim fallback is only
    used for original worlds (and known-IP characters that are not in the
    IP knowledge pack — e.g., admin-added supporting characters).
    """

    name: str
    name_english: str = ""
    # When set: short phrase like "《逐玉》里的武安侯，化名言正".
    # When None: 4-dim fallback fields below must be populated.
    reference_anchor: str | None = None
    # 4-dim fallback — required when reference_anchor is None; ignored otherwise.
    gender: Literal["男", "女", ""] = ""
    age_band: str = ""  # 少年 / 少女 / 青年 / 中年 / 老年
    role_class: str = ""  # 武将 / 文官 / 屠户 / 宰相 / 工人 / 科学家 / ...
    # mood_anchor is appended for both ref + fallback paths (a 4-8 char emotional cue).
    mood_anchor: str = ""


class EndingCoverBrief(BaseModel):
    """Per-ending brief for ending card generation."""

    title: str
    title_english: str = ""
    description: str = Field(
        ...,
        description=(
            "1–2 句话描述故事到这一结局的状态。结局本身就是剧透，可以含具体情节；"
            "但避免血腥/暴力的直白描写——用象征性表达（光束、空椅、远去的人影）"
        ),
    )


# ---------------------------------------------------------------------------
# Derivation helpers (the mechanical ones; mood + English names live in
# cover_brief_helper.py because they need LLM judgment)
# ---------------------------------------------------------------------------


# IPRecognition confidence floor for promoting a hint to a hard ip_name.
# Below this we discard the IP name and let the model run un-anchored —
# better than feeding a low-confidence guess that misleads the visual DNA.
IP_NAME_CONFIDENCE_FLOOR = 0.6


def derive_character_reference_anchor(
    *,
    character_name: str,
    ip_name: str | None,
    ip_pack: IPKnowledgePack | None,
) -> str | None:
    """Build a character ``reference_anchor`` from the IP knowledge pack.

    Returns ``None`` when:
    - ip_name is unknown, OR
    - ip_pack is missing, OR
    - the character is not in the IP pack (e.g., admin added a new supporting
      character to a known-IP world). In that case caller should fall back to
      the 4-dim descriptor path.

    Format: ``"《{ip_name}》里的{role_in_story}"`` — kept deliberately minimal
    because the V-series experiments showed that the model fills in occupation
    /era details correctly from training when the IP + role are named.
    """
    if not ip_name or ip_pack is None:
        return None
    ip_clean = ip_name.strip()
    if not ip_clean:
        return None
    for ip_char in ip_pack.characters:
        if (ip_char.name or "").strip() != (character_name or "").strip():
            continue
        role = (ip_char.role_in_story or "").strip()
        return f"《{ip_clean}》里的{role}" if role else f"《{ip_clean}》里的{character_name}"
    return None


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

# Shared trailing negative. Kept short — the validation experiments showed that
# long negative lists do not improve compliance and sometimes confuse the model.
# 演员表 added 2026-06-23: gpt-image-2 likes to render a cast-credit strip at the
# bottom of poster-style key art; naming it explicitly removes it (user feedback).
_LOGO_NEGATIVE = "不要出现 logo、品牌、演员表、奖项、发行日期、电视台署名。"

# Cinematic KEY ART framing + anti-collage.
#
# 2026-06-15 这里曾改成"电影剧照 / 像一帧电影镜头" + 明令"不要海报感"，目的是治大 IP 的
# montage 失败模式（模型把龙椅+龙纹+地图所有标志元素堆成一张过饱和拼贴海报）。但这是
# 矫枉过正：剧照=平铺单帧截图，把 gpt-image-2 最擅长的"讲究构图 + 戏剧光影"的影视级 key
# art 能力一起压住了。2026-06-23 用户实测「影视级海报 + 不要 logo/演员表」远好于现状——
# 真正的病不是"海报形态"而是 montage + logo/演员表/字幕这些商业垃圾。
#
# 现版本：拥抱影视级海报 / 电影 key art 的质感（构图、光影、景深、高级感），但保留反 montage
# （单一统一焦点、不堆砌拼贴）。商业垃圾交给 _LOGO_NEGATIVE 兜。
_CINEMATIC_COHESION = (
    "整体呈现影视级海报 / 电影 key art 的质感：构图讲究、有明确视觉主体、"
    "戏剧性的光影与景深，精致考究、有高级感。"
    "保持单一、浑然一体的画面与统一焦点，不要把多个标志性元素拼贴、分屏或堆叠成大杂烩。"
)

# The site UI is near-black (--lv-bg #08080a). Without a nudge the model tends
# to muddy images into that darkness; covers then disappear on the page. This
# is defensive (avoid murky/oppressive), NOT a hard "make it bright" — so a
# deliberately moody world (e.g. 民国 watercolor grey) keeps its tone while
# staying legible. Feedback: 图配暗色网站要通透、别压抑死黑.
_DARK_UI_HINT = "画面会在深色网站上陈列，整体保持通透、避免晦暗压抑。"


def _world_subject_and_essence(brief: CoverBrief, ip_fallback: bool = False) -> tuple[str, str]:
    """Decide how the model gets to *understand* this world.

    IP world (``ip_name`` set): name the IP and let the model paint the canon —
    the IP name is a richer, more complete anchor than any hand-written scene
    list, and the model knows the IP better than we do. No essence injected.

    ``ip_fallback`` softens the anchor from "为《IP》"(paint the canon) to
    "视觉对标《IP》系列"(reference the look). Strong Western IPs get the direct
    form moderation-blocked on some endpoints; the reference form is proven to
    pass while keeping the visual DNA. Callers escalate to it on a blocked
    (empty) result.

    Original world: the ``essence`` (= description) is the model's only window
    into the world, so it's injected verbatim before the subject clause.

    Returns ``(subject_clause, essence_clause)``; essence_clause is "" for IP
    worlds and for originals with no description.
    """
    if brief.ip_name and brief.ip_name.strip():
        ip = brief.ip_name.strip()
        if ip_fallback:
            return f"视觉对标《{ip}》系列，为同类题材的虚构作品", ""
        return f"为《{ip}》", ""
    ess = (brief.essence or "").strip()
    essence_clause = f"以下是这个世界的内核，请理解后创作：{ess}\n" if ess else ""
    return f"为虚构作品《{brief.world_name}》", essence_clause


def _mood_clause(mood: str) -> str:
    """Inject mood cue. Empty mood degrades to no clause (mood ablation
    experiment showed quality drops sharply for ORIGINAL worlds; keep this for
    the loud failure rather than silently masking it).

    IP worlds pass '' here (call sites gate on ip_name): the IP name is a far
    richer anchor than our hand-derived mood, and injecting a mood cue biases
    the model toward our reading (e.g. 唐诡 → grimdark) instead of letting it
    free-create from what it knows about the work. The ablation finding only
    held for originals (no IP to anchor on)."""
    m = (mood or "").strip()
    if not m:
        return ""
    # Plain style direction. The old "可作为画面元素自然出现" wording nudged the
    # model to *add* decorative props (the 花里胡哨 problem) — dropped.
    return f"画面风格：{m}。"


def build_world_hero_prompt(brief: CoverBrief, ip_fallback: bool = False) -> str:
    """21:9 cinematic hero. Used for full-screen spotlight on /discover and
    /worlds/[id]. The prompt never mentions titles: every surface renders the
    world name in the system font, and even a "no title" instruction tends to
    make the model paint one — so we stay silent about it entirely.

    ``ip_fallback`` (see ``_world_subject_and_essence``) is set on a retry when
    the direct IP form gets moderation-blocked.
    """
    subject, essence = _world_subject_and_essence(brief, ip_fallback)
    return (
        f"{essence}"
        f"{subject}创作一幅 21:9 的代表性画面，用于网站首页全屏陈列。"
        "请理解这个作品的整体氛围与精神内核后自由创作，由你决定最能传达它气质的意象与构图。"
        f"{_CINEMATIC_COHESION}"
        f"{_mood_clause('' if (brief.ip_name or '').strip() else brief.mood)}"
        f"{_DARK_UI_HINT}"
        f"{_LOGO_NEGATIVE}"
    )


def build_world_cover_prompt(brief: CoverBrief, ip_fallback: bool = False) -> str:
    """3:2 list-card cover. Independent generation (not cropped from hero).

    Like every builder, the prompt never mentions titles: the UI renders the
    world name in the system font, and naming "title" at all (even to forbid it)
    just makes the model want to draw one. The 280px usage hint lets it reason
    about composition on its own. ``ip_fallback`` mirrors the hero builder.
    """
    subject, essence = _world_subject_and_essence(brief, ip_fallback)
    return (
        f"{essence}"
        f"{subject}创作一幅 3:2 的封面图，用于网站世界列表里的小尺寸卡片陈列，"
        "缩略到 280px 宽时仍要一眼传达这个作品的整体气质。"
        "请理解它的内核后自由创作，聚焦一个核心意象。"
        f"{_CINEMATIC_COHESION}"
        f"{_mood_clause('' if (brief.ip_name or '').strip() else brief.mood)}"
        f"{_DARK_UI_HINT}"
        f"{_LOGO_NEGATIVE}"
    )


def build_script_cover_prompt(
    world_brief: CoverBrief,
    *,
    script_title: str,
    script_title_english: str,
    script_essence: str = "",
    ip_fallback: bool = False,
) -> str:
    """3:2 cover for a script (a story line within a world).

    Fed the script's own essence (its hook / central conflict) so the image
    reflects *this story line*, not just the world. IP worlds anchor on the IP
    name; originals on the world name. ``ip_fallback`` softens an IP world's
    anchor to "视觉对标" on a moderation-blocked retry.
    """
    ip = (world_brief.ip_name or "").strip()
    if ip and ip_fallback:
        head = f"视觉对标《{ip}》系列，为其中的剧情线《{script_title}》创作一幅 3:2 的代表性画面。"
    elif ip:
        head = f"为《{ip}》中的剧情线《{script_title}》创作一幅 3:2 的代表性画面。"
    else:
        head = f"为《{world_brief.world_name}》中的剧情线《{script_title}》创作一幅 3:2 的代表性画面。"
    ess = (script_essence or "").strip()
    ess_clause = f"以下是这条剧情线的内核，请理解后创作：{ess}\n" if ess else ""
    return (
        f"{ess_clause}{head}"
        "请理解这段故事的张力后自由创作，由你决定最能传达它的意象与构图，不必罗列写实场景。"
        f"{_mood_clause('' if ip else world_brief.mood)}"
        f"{_DARK_UI_HINT}"
        f"{_LOGO_NEGATIVE}"
    )


def _character_descriptor(char: CharacterCoverBrief) -> str:
    """Build the parenthetical descriptor — ref anchor preferred, 4-dim fallback."""
    if char.reference_anchor:
        anchor = char.reference_anchor.strip()
        return f"{anchor}；{char.mood_anchor}" if char.mood_anchor else anchor
    parts: list[str] = []
    if char.gender:
        parts.append(f"{char.gender}性")
    if char.age_band:
        parts.append(char.age_band)
    if char.role_class:
        parts.append(char.role_class)
    if char.mood_anchor:
        parts.append(char.mood_anchor)
    return "，".join(parts) if parts else "虚构角色"


def build_character_portrait_prompt(
    world_brief: CoverBrief, char: CharacterCoverBrief
) -> str:
    """2:3 character portrait, no painted name text.

    Name labeling is handled by the UI overlay, not the image — generated text
    in Chinese is unstable (wrong characters, awkward fonts) and would collide
    with the card title anyway. Eye-line on the upper third is required for
    the front-end's automatic circular avatar crop. Style cue "《world》风格的"
    is included only when the world is IP-anchored.
    """
    descriptor = _character_descriptor(char)
    style_cue = (
        f"《{world_brief.world_name}》风格的 "
        if world_brief.ip_name and world_brief.ip_name.strip()
        else ""
    )
    return (
        f"为《{world_brief.world_name}》中的角色「{char.name}」（{descriptor}）"
        f"创作一幅{style_cue}2:3 人物海报。"
        "眼线落在画面上三分位附近（前端将自动裁出圆形头像）。"
        "画面中不要出现任何文字、姓名标签或字幕。"
        f"{_LOGO_NEGATIVE}"
        "2:3 竖版。"
    )


def build_ending_card_prompt(
    world_brief: CoverBrief, ending: EndingCoverBrief
) -> str:
    """3:2 ending card. ``ending.description`` IS the spoiler — endings are
    only shown after the player reaches them, so it's a legitimate spoiler
    moment, not a privacy leak. The ``无血腥暴力直白展示`` clause keeps
    death/violence endings symbolic rather than graphic.
    """
    return (
        f"为《{world_brief.world_name}》创作一张「{ending.title}」结局画面卡。"
        f"故事到这里的状态：{ending.description}"
        f"{_mood_clause(world_brief.mood)}"
        f"若画面包含标题文字，使用「{ending.title}」。"
        "无血腥暴力直白展示，可象征性表达。"
        f"{_LOGO_NEGATIVE}"
        "3:2 横版。"
    )


__all__ = [
    "CoverBrief",
    "CharacterCoverBrief",
    "EndingCoverBrief",
    "IP_NAME_CONFIDENCE_FLOOR",
    "derive_character_reference_anchor",
    "build_world_hero_prompt",
    "build_world_cover_prompt",
    "build_script_cover_prompt",
    "build_character_portrait_prompt",
    "build_ending_card_prompt",
]
