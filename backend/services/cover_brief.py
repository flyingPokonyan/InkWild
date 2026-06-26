"""Cover image brief — drives all cover/hero/script/portrait/ending prompts.

V4 (2026-06-26) 画法体系. 取代 V3 的"厚涂插画地基 + 明度调参"路线，整体重写。

核心理念（经 5 轮 prod A/B 验证，见 docs/design/image-style-direction.md）：

  每张封面 = **AI 按题材选一种强风格化画法** + **一套克制手艺纪律**。
  媒介是「画」，明度由画法与题材自带，不单独调参。

为什么这么定：
- discover 廉价的真根源不是亮暗/饱和，是「画法」——之前用「厚涂概念美术」(digital
  painting / concept art)，它是「最写实的插画」，离照片最近、AI 最擅长出，所以最廉价、
  最有 AI 味。在它上面调明度（暗→亮→L3 讨喜）全是给廉价底子化妆。
- 换成水墨/工笔/版画/水彩/扁平/丝网/浮世绘/绘本/钢笔/新艺术/蜡笔/拼贴这些**有强烈艺术
  语言**的画法，每一种都甩开厚涂一大截：因为它们有「画家的取舍 + 留白 + 风格化语言」。
- 不同题材配不同画法 → 同时解决「高级」与「不同质化」。12 种画法铺开仍收得住，因为每张
  都守同一套**手艺纪律**（大留白 / 单一焦点 / 一抹点睛色 / 反厚涂渲染）—— House Style
  钉的是这套「克制纪律」，不是某一种画法。

art_style 由 ``cover_brief_helper`` 在派生 brief 时让 LLM 一并选出（按世界气质，从
``STYLE_DESC`` 池里挑最配的一种）；空值 fallback 到 ``ART_STYLE_FALLBACK``。

mood（V3 的画面气质 cue）在 V4 **不再注入** world cover/hero/script prompt——art_style
+ essence 已足够（ai_style 实验无 mood 时最惊艳），且 mood 的「色调/氛围」会与画法打架。
``CoverBrief.mood`` 字段保留（向后兼容；角色用的是 ``mood_anchor``）。

The whole brief is reconstructed on-the-fly each generation run; nothing is
persisted (``worlds.visual_brief`` / ``scripts.visual_brief`` were dropped in
migration ``9a8b7c6d5e4f``).
"""
from __future__ import annotations

import hashlib
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
    ``world_name_english`` / ``mood`` / ``art_style`` are filled by
    ``cover_brief_helper`` in a single LLM call; the rest is mechanical.
    """

    world_name: str
    world_name_english: str = ""
    genre_tag: str = ""  # short era+genre phrase, e.g. "古装权谋" / "民国谍战"
    # V4: the画法 AI picked for this world (a key of ``STYLE_DESC``). Empty →
    # falls back to ``ART_STYLE_FALLBACK``. This is the core visual driver.
    art_style: str = ""
    # V4: the LLM-constructed 画面核心 — the one hook-y image that best
    # represents this world. Frees "画什么" from the default "single人物"; can be
    # a person / scene / moment / object as the world dictates. Empty → builders
    # fall back to essence + 画法 (model free-composes).
    cover_focus: str = ""
    # V3 画面气质 cue 词. Retained for back-compat but NOT injected into V4
    # world prompts (art_style + essence cover it; mood's 色调/氛围 fights the
    # 画法). See module docstring.
    mood: str = ""
    # Reference IP name when the world borrows visual DNA from a known title
    # (e.g. world_name="凡尘仙途", ip_name="诛仙"). Equal to world_name when
    # the world IS the IP. None when original / IP recognizer didn't fire.
    ip_name: str | None = None
    # World essence (= the world's description). For ORIGINAL worlds this is the
    # model's only window into what the world is about, so it's injected into the
    # hero/cover prompt verbatim. For IP worlds it's ignored: the IP name is a
    # far richer anchor than any description.
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
# 画法池 (STYLE_DESC) — the source of truth for available art styles.
# ``cover_brief_helper`` shows these keys to the LLM and asks it to pick one
# per world; the builders look the picked key up here for the prompt clause.
# Every entry is a STRONG stylized medium with its own artistic language —
# never "厚涂概念美术/digital painting", which is the廉价 baseline we replaced.
# ---------------------------------------------------------------------------

STYLE_DESC: dict[str, str] = {
    "水墨写意": "中国水墨写意——墨色浓淡干湿、飞白、大面积留白、寥寥数笔概括神韵，重意境，宣纸肌理。",
    "工笔重彩": "中国工笔重彩——精细勾线、矿物颜料的沉稳重彩、装饰性的图案与金线，典雅考究。",
    "铜版木刻": "复古铜版画 / 木刻版画——硬朗刻线、有限套色、平面化、强烈黑白灰关系与装饰肌理，像古籍插图。",
    "水彩淡彩": "水彩 / 钢笔淡彩——透明轻盈的水彩晕染、湿边、大量留白、概括形体，雅致书籍插画感。",
    "扁平极简": "现代扁平插画——限定几个主色、大色块、概括的几何形体、装饰性平面构图、大胆留白，不画写实光影。",
    "丝网波普": "丝网印刷 / 波普平面海报——高对比平面色块、套色错位质感、简练有力的图形语言、强装饰性。",
    "浮世绘": "日本浮世绘 / 木版画——平涂色块、装饰性的线条与波纹、留白、传统东方版画构图。",
    "复古绘本": "复古童书 / 绘本插画——温暖手绘、柔和颗粒质感、概括造型，有故事书般的亲切感。",
    "钢笔线描": "钢笔线描 + 单色淡彩——纤细灵动的线条、克制的局部上色、大量留白，文学速写感。",
    "新艺术装饰": "新艺术运动装饰风（Art Nouveau）——流畅曲线、装饰性边框、平面化、华丽而克制的图案感。",
    "蜡笔色粉": "蜡笔 / 色粉 / 干笔触——粗粝温暖的笔触肌理、柔和的色彩过渡、手作感、概括的形体。",
    "拼贴构成": "拼贴 / 构成主义——纸张拼贴、几何分割、错位的图形与肌理、强设计感的平面构成。",
}

# Fallback when art_style is empty / unknown (legacy worlds, LLM miss). A safe,
# universally-flattering 留白 medium — never falls back to 厚涂.
ART_STYLE_FALLBACK = "水彩淡彩"


def resolve_style_desc(art_style: str | None) -> str:
    """Look up a 画法 description, falling back to ART_STYLE_FALLBACK."""
    key = (art_style or "").strip()
    return STYLE_DESC.get(key) or STYLE_DESC[ART_STYLE_FALLBACK]


# 题材大类 → 候选画法池. The LLM classifies the world into one of these
# categories (regular, coarse); the code then picks ONE style from the pool by
# hashing the world name. This is what fixes同质化: letting the LLM pick the
# style directly (per-world, no global view) collapsed every 古风 world onto
# 工笔重彩. Genre→candidate-pool + name-hash spreads same-genre worlds across
# several fitting styles, deterministically (a world keeps its style on regen)
# and works per-world (no global rebalance needed). Every candidate is a strong
# stylized medium that suits the category.
GENRE_STYLE_POOL: dict[str, list[str]] = {
    "古风宫廷": ["工笔重彩", "水墨写意", "浮世绘", "新艺术装饰"],
    "武侠仙侠": ["水墨写意", "浮世绘", "工笔重彩", "钢笔线描"],
    "赛博科幻": ["丝网波普", "扁平极简", "拼贴构成"],
    "末世废土": ["拼贴构成", "铜版木刻", "丝网波普"],
    "悬疑推理": ["铜版木刻", "钢笔线描", "水彩淡彩", "新艺术装饰"],
    "民国谍战": ["钢笔线描", "水彩淡彩", "铜版木刻"],
    "现代都市": ["水彩淡彩", "扁平极简", "蜡笔色粉"],
    "校园日常": ["蜡笔色粉", "复古绘本", "水彩淡彩"],
    "奇幻童话": ["复古绘本", "新艺术装饰", "水彩淡彩", "浮世绘"],
    "恐怖诡秘": ["新艺术装饰", "铜版木刻", "钢笔线描"],
    "其他": ["水彩淡彩", "水墨写意", "扁平极简", "铜版木刻", "蜡笔色粉"],
}


def pick_art_style(genre_category: str | None, world_name: str) -> str:
    """Pick a 画法 from the genre's candidate pool by hashing the world name.

    Deterministic (same world → same style across regens), and spreads
    same-genre worlds across the pool instead of all collapsing on one style.
    Unknown category → "其他" pool.
    """
    pool = GENRE_STYLE_POOL.get((genre_category or "").strip()) or GENRE_STYLE_POOL["其他"]
    h = int(hashlib.md5((world_name or "").encode("utf-8")).hexdigest(), 16)
    return pool[h % len(pool)]


# ---------------------------------------------------------------------------
# Derivation helpers (the mechanical ones; mood + English names + art_style
# live in cover_brief_helper.py because they need LLM judgment)
# ---------------------------------------------------------------------------


# IPRecognition confidence floor for promoting a hint to a hard ip_name.
# Below this we discard the IP name and let the model run un-anchored.
IP_NAME_CONFIDENCE_FLOOR = 0.6


def derive_character_reference_anchor(
    *,
    character_name: str,
    ip_name: str | None,
    ip_pack: IPKnowledgePack | None,
) -> str | None:
    """Build a character ``reference_anchor`` from the IP knowledge pack.

    Returns ``None`` when ip_name is unknown, ip_pack is missing, or the
    character is not in the IP pack (caller falls back to the 4-dim descriptor).
    Format ``"《{ip_name}》里的{role_in_story}"`` — minimal because the V-series
    experiments showed the model fills occupation/era from training when IP +
    role are named.
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
# Prompt building blocks
# ---------------------------------------------------------------------------

# Shared trailing negative. Explicit about readable text: batch covers showed
# random Chinese signs / countdown digits / poster titles, which look dirty in
# the UI because InkWild renders all metadata itself.
_LOGO_NEGATIVE = (
    "画面里不要任何可读文字、标题、字幕、数字、乱码、logo、品牌、演员表、奖项、发行日期、"
    "署名或界面元素；牌匾、纸张、卷轴、符咒只能作为模糊纹理，不要生成可辨认字符。"
)

# Craft discipline = the V4 House Style. NOT a particular look — a set of
# restraint rules every 画法 must obey, which is what holds the multi-style
# batch together (留白 / single focus / one accent / anti-厚涂).
_CRAFT_DISCIPLINE = (
    "用这种画法去『表达』，而不是把场景渲染逼真：敢于大胆留白、概括取舍、宁简勿满，"
    "构图有清晰的焦点、一抹克制的点睛色，体现明确的手绘艺术语言。"
    "画面铺满整个画幅、延伸到四条边，不要任何内嵌画框、装饰边框或留边。"
    "避免面面俱到的写实厚涂渲染、3D 渲染感、塑料质感、照片感、HDR、信息过载、"
    "廉价 stock 感、二游立绘与网文封面感。媒介始终是「画」，不是照片。"
)

# Web legibility floor. Luminosity is left to the 画法 + 题材 (NOT forced bright
# or dark — that lesson cost us several rounds); this only guards against muddy
# /unreadable images on the near-black (--lv-bg #08080a) card grid.
_WEB_LEGIBILITY = (
    "画面会陈列在近黑色、香槟金点缀的网站卡片与大图区域；明暗由画法与题材自定，"
    "但即使是暗画面也要透气、有空气感，暗部不要糊成死黑一团或脏乱颗粒、高光不要过曝发白，"
    "整体在卡片上清楚可读。"
)


def _style_clause(brief: CoverBrief) -> str:
    """The core V4 clause: the picked 画法 + the craft discipline."""
    return f"画法：{resolve_style_desc(brief.art_style)}{_CRAFT_DISCIPLINE}"


def _focus_clause(brief: CoverBrief) -> str:
    """The LLM-distilled 主题钩子 (theme + emotional hook, NOT a摆拍 spec). Gives
    gpt-image a direction to break the "全是单人+留白" sameness, but leaves the
    actual composition / framing / who's in it to the image model's own发挥
    (A/B-tested: 摆拍指令 frames it too tight; 主题钩子 keeps gpt-image's
    creativity while steering it on-theme). Empty → no clause, free-compose."""
    focus = (brief.cover_focus or "").strip()
    return (
        f"这张封面要传达：{focus}——由你构想最能一眼勾住人的那个画面，画什么、什么构图都由你发挥。"
        if focus else ""
    )


def _world_subject_and_essence(brief: CoverBrief, ip_fallback: bool = False) -> tuple[str, str]:
    """Decide how the model gets to *understand* this world.

    IP world (``ip_name`` set): name the IP and let the model paint the canon.
    ``ip_fallback`` softens "为《IP》" → "视觉对标《IP》系列" for strong Western
    IPs that get moderation-blocked on the direct form.

    Original world: the ``essence`` (= description) is injected verbatim.

    Returns ``(subject_clause, essence_clause)``.
    """
    if brief.ip_name and brief.ip_name.strip():
        ip = brief.ip_name.strip()
        if ip_fallback:
            return f"视觉对标《{ip}》系列，为同类题材的虚构作品", ""
        return f"为《{ip}》", ""
    ess = (brief.essence or "").strip()
    essence_clause = f"以下是这个世界的内核，请理解后创作：{ess}\n" if ess else ""
    return f"为虚构作品《{brief.world_name}》", essence_clause


def _fidelity_clause(brief: CoverBrief) -> str:
    """Keep source/IP recognition above the house display layer. The 画法 does
    the translating — IP worlds keep their era/material DNA but are rendered in
    the picked 画法, never as a photorealistic still / official poster."""
    ip = (brief.ip_name or "").strip()
    if ip:
        return (
            f"原作/已知 IP 识别优先：保留《{ip}》的时代质感、题材气质、人物关系、"
            "核心意象与服饰建筑，但用上述画法转译，不要复刻官方写实剧照或海报。"
        )
    return "忠实这个世界的内核与气质，不要套通用模板。"


def build_world_hero_prompt(brief: CoverBrief, ip_fallback: bool = False) -> str:
    """21:9 hero for full-screen spotlight. Never mentions titles (the UI renders
    the world name; naming "title" makes the model paint one)."""
    subject, essence = _world_subject_and_essence(brief, ip_fallback)
    return (
        f"{essence}"
        f"{subject}创作一幅 21:9 的代表性画面，用于网站首页全屏沉浸陈列，一眼传达这个作品的气质。"
        f"{_focus_clause(brief)}"
        f"{_style_clause(brief)}"
        f"{_fidelity_clause(brief)}"
        f"{_WEB_LEGIBILITY}"
        f"{_LOGO_NEGATIVE}"
    )


def build_world_cover_prompt(brief: CoverBrief, ip_fallback: bool = False) -> str:
    """3:2 list-card cover. Independent generation (not cropped from hero)."""
    subject, essence = _world_subject_and_essence(brief, ip_fallback)
    return (
        f"{essence}"
        f"{subject}创作一幅 3:2 的封面图，用于网站世界列表的小尺寸卡片陈列，"
        "缩略到 280px 宽时仍要一眼传达气质。"
        f"{_focus_clause(brief)}"
        f"{_style_clause(brief)}"
        f"{_fidelity_clause(brief)}"
        f"{_WEB_LEGIBILITY}"
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
    """3:2 cover for a script (a story line within a world). Uses the world's
    art_style so a world's scripts share its 画法."""
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
        f"{ess_clause}{head}聚焦最能传达它张力的单一意象，不必罗列写实场景。"
        f"{_style_clause(world_brief)}"
        f"{_fidelity_clause(world_brief)}"
        f"{_WEB_LEGIBILITY}"
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
    """2:3 character portrait in the world's 画法. Unlike covers, portraits keep
    a hard "clear face on the upper third" constraint for the front-end's
    circular avatar crop — so the 画法 styles the face but must not abstract it
    away (no pure silhouette / faceless collage)."""
    descriptor = _character_descriptor(char)
    return (
        f"为《{world_brief.world_name}》中的角色「{char.name}」（{descriptor}）创作一幅 2:3 人物主视觉。"
        f"画法：{resolve_style_desc(world_brief.art_style)}"
        "用这种画法的笔触与肌理塑造人物，但人物要有清晰可辨的面部、半身或胸像构图，"
        "眼线落在画面上三分位附近（前端将自动裁出圆形头像）；不要纯剪影或抹去五官。"
        "不要照相写实渲染、塑料皮肤或过度磨皮。"
        f"{_fidelity_clause(world_brief)}"
        "画面中不要出现任何文字、姓名标签或字幕。"
        f"{_WEB_LEGIBILITY}"
        f"{_LOGO_NEGATIVE}"
        "2:3 竖版。"
    )


def build_ending_card_prompt(
    world_brief: CoverBrief, ending: EndingCoverBrief
) -> str:
    """3:2 ending card in the world's 画法. ``ending.description`` IS the spoiler
    (endings show only after the player reaches them)."""
    return (
        f"为《{world_brief.world_name}》创作一张「{ending.title}」结局画面卡。"
        f"故事到这里的状态：{ending.description}"
        f"{_style_clause(world_brief)}"
        f"{_fidelity_clause(world_brief)}"
        "无血腥暴力直白展示，可象征性表达。"
        f"{_WEB_LEGIBILITY}"
        f"{_LOGO_NEGATIVE}"
        "3:2 横版。"
    )


__all__ = [
    "CoverBrief",
    "CharacterCoverBrief",
    "EndingCoverBrief",
    "STYLE_DESC",
    "ART_STYLE_FALLBACK",
    "GENRE_STYLE_POOL",
    "resolve_style_desc",
    "pick_art_style",
    "IP_NAME_CONFIDENCE_FLOOR",
    "derive_character_reference_anchor",
    "build_world_hero_prompt",
    "build_world_cover_prompt",
    "build_script_cover_prompt",
    "build_character_portrait_prompt",
    "build_ending_card_prompt",
]
