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

art_style 由 ``cover_brief_helper`` 派生出的 genre_category / culture / style_scores
驱动，最终由代码执行文化硬过滤 + 题材池 + 确定性加权 hash 选出；空值 fallback 到
``ART_STYLE_FALLBACK``。LLM 参与审美排序，但不绕过白名单和文化边界。

mood（V3 的画面气质 cue）在 V4 **不再注入** world cover/hero/script prompt——art_style
+ essence 已足够（ai_style 实验无 mood 时最惊艳），且 mood 的「色调/氛围」会与画法打架。
``CoverBrief.mood`` 字段保留（向后兼容；角色用的是 ``mood_anchor``）。

The whole brief is reconstructed on-the-fly each generation run; nothing is
persisted (``worlds.visual_brief`` / ``scripts.visual_brief`` were dropped in
migration ``9a8b7c6d5e4f``).
"""
from __future__ import annotations

import hashlib
from typing import Any, Literal

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
    # Coarse cultural language. Used as a hard guardrail before style hash
    # selection so Chinese palace intrigue cannot fall into European/Japanese
    # print traditions, while neutral media remain available.
    culture: str = ""
    # The LLM's coarse genre bucket. Persisted for debug/reuse; final art_style
    # is still code-selected from the genre pool under culture constraints.
    genre_category: str = ""
    # V4: the画法 AI picked for this world (a key of ``STYLE_DESC``). Empty →
    # falls back to ``ART_STYLE_FALLBACK``. This is the core visual driver.
    art_style: str = ""
    # Sanitized LLM style scores used for deterministic weighted selection.
    # Persisted only for debugging/reuse, never trusted without whitelist +
    # culture filtering.
    style_scores: list[dict[str, Any]] = Field(default_factory=list)
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
    # De-IP'd visual phrase (hair/build/attire/vibe, NO proper names / trademark
    # markers) used ONLY by the ip_fallback portrait tier when the direct IP
    # anchor is moderation-blocked on 与第三方内容相似性. Keeps the character's
    # general look while dropping the copyright-identifying features.
    deip_hint: str = ""


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
    "青绿山水": "中国青绿山水——石青石绿为主色、金碧勾勒点缀、云雾缥缈留白、山势高远出尘，仙气典雅，绢本设色肌理。",
    "工笔重彩": "中国工笔重彩——精细勾线、矿物颜料的沉稳重彩、装饰性的图案与金线，典雅考究。",
    "古籍绣像": "中国明清古籍绣像 / 小说木刻插图——朱墨套色、硬朗刻线、章回小说插图感、旧宣纸与古籍纸张肌理，冷峻克制；不要浮世绘、不要日式红日与浪纹。",
    "民国画报": "民国画报 / 连环画淡彩——旧上海与近代报刊插画气质、石印画报颗粒、钢笔线稿与克制套色，像旧杂志故事封面；不要广告美女月份牌套路。",
    "铜版木刻": "欧洲 19 世纪古籍铜版画 / 木刻版画——硬朗刻线、交叉排线、有限套色、平面化、强烈黑白灰关系与装饰肌理；不要浮世绘、不要日式红日与浪纹。",
    "水彩淡彩": "水彩 / 钢笔淡彩——透明轻盈的水彩晕染、湿边、大量留白、概括形体，雅致书籍插画感。",
    "扁平极简": "现代扁平插画——限定几个主色、大色块、概括的几何形体、装饰性平面构图、大胆留白，不画写实光影。",
    "丝网波普": "丝网印刷 / 波普平面海报——高对比平面色块、套色错位质感、简练有力的图形语言、强装饰性。",
    "浮世绘": "日本浮世绘 / 木版画——平涂色块、装饰性的线条与波纹、留白、传统东方版画构图。",
    "复古绘本": "复古童书 / 绘本插画——温暖手绘、柔和颗粒质感、概括造型，有故事书般的亲切感。",
    "钢笔线描": "钢笔线描 + 单色淡彩——纤细灵动的线条、克制的局部上色、大量留白，文学速写感。",
    "新艺术装饰": "新艺术运动装饰风（Art Nouveau）——流畅曲线、装饰性边框、平面化、华丽而克制的图案感。",
    "蜡笔色粉": "蜡笔 / 色粉 / 干笔触——粗粝温暖的笔触肌理、柔和的色彩过渡、手作感、概括的形体。",
    "拼贴构成": "拼贴 / 构成主义——纸张拼贴、几何分割、错位的图形与肌理、强设计感的平面构成。",
    "黑白漫画": "黑白图像小说 / 漫画分镜插画——高对比黑白、粗细变化的墨线、少量网点与阴影块，叙事张力强，像严肃 graphic novel 封面；不要日漫二次元表情。",
    "档案拼贴": "档案拼贴 / 旧报纸调查板——旧照片边缘、剪报、票据、地图线索与克制红线标记组成的文学调查封面，主视觉仍清晰，不要杂乱 scrapbook。",
}

# Fallback when art_style is empty / unknown (legacy worlds, LLM miss). A safe,
# universally-flattering 留白 medium — never falls back to 厚涂.
ART_STYLE_FALLBACK = "水彩淡彩"


def resolve_style_desc(art_style: str | None) -> str:
    """Look up a 画法 description, falling back to ART_STYLE_FALLBACK."""
    key = (art_style or "").strip()
    return STYLE_DESC.get(key) or STYLE_DESC[ART_STYLE_FALLBACK]


# 文化语系 → allowed style tags. "通用" styles survive every culture filter.
# The hard filter is the fix for failures like Chinese court intrigue landing
# on European/Japanese print languages.
STYLE_CULTURE_TAGS: dict[str, set[str]] = {
    "工笔重彩": {"中式古典"},
    "水墨写意": {"中式古典"},
    "青绿山水": {"中式古典"},
    "古籍绣像": {"中式古典"},
    "民国画报": {"中式近现代"},
    "浮世绘": {"日式和风"},
    "铜版木刻": {"西方古典", "中式近现代", "现代中性"},
    "新艺术装饰": {"西方古典"},
    "水彩淡彩": {"通用"},
    "钢笔线描": {"通用"},
    "复古绘本": {"通用"},
    "蜡笔色粉": {"通用"},
    "扁平极简": {"现代中性"},
    "丝网波普": {"现代中性"},
    "拼贴构成": {"现代中性", "中式近现代"},
    "黑白漫画": {"通用"},
    "档案拼贴": {"现代中性", "中式近现代", "西方古典"},
}

CULTURE_CATEGORIES = {"中式古典", "中式近现代", "日式和风", "西方古典", "现代中性"}


def style_allowed_for_culture(style: str, culture: str | None) -> bool:
    """Return whether ``style`` may be used under ``culture``.

    Unknown/empty culture keeps legacy behavior and allows all valid styles.
    """
    if style not in STYLE_DESC:
        return False
    c = (culture or "").strip()
    if not c or c not in CULTURE_CATEGORIES:
        return True
    tags = STYLE_CULTURE_TAGS.get(style, {"通用"})
    return "通用" in tags or c in tags


# 题材大类 → 候选画法池. The LLM classifies the world into one of these
# categories (regular, coarse); the code then picks ONE style from the pool by
# deterministic hash, optionally weighted by LLM style_scores after culture
# filtering. This keeps same-genre worlds varied without letting the LLM freely
# choose a final style.
GENRE_STYLE_POOL: dict[str, list[str]] = {
    "古风宫廷权谋": ["工笔重彩", "水墨写意", "古籍绣像", "青绿山水"],
    "古风宫廷": ["工笔重彩", "水墨写意", "古籍绣像", "青绿山水"],
    "古风言情": ["工笔重彩", "水彩淡彩", "水墨写意", "复古绘本"],
    "中式古代悬疑": ["古籍绣像", "钢笔线描", "水彩淡彩", "水墨写意", "黑白漫画"],
    "武侠仙侠": ["水墨写意", "青绿山水", "水彩淡彩", "钢笔线描"],
    "民国谍战": ["民国画报", "钢笔线描", "水彩淡彩", "铜版木刻", "档案拼贴"],
    "近现代中国悬疑": ["水彩淡彩", "钢笔线描", "复古绘本", "档案拼贴", "黑白漫画"],
    "西方古典悬疑": ["铜版木刻", "新艺术装饰", "钢笔线描", "水彩淡彩", "黑白漫画"],
    "西方奇幻哥特": ["新艺术装饰", "铜版木刻", "水彩淡彩", "复古绘本", "黑白漫画"],
    "东瀛和风": ["浮世绘", "水彩淡彩", "钢笔线描", "黑白漫画"],
    "恐怖灵异": ["铜版木刻", "古籍绣像", "浮世绘", "钢笔线描", "黑白漫画", "档案拼贴"],
    "赛博科幻": ["丝网波普", "扁平极简", "拼贴构成", "钢笔线描", "黑白漫画"],
    "硬科幻": ["扁平极简", "钢笔线描", "水彩淡彩", "拼贴构成", "黑白漫画"],
    "末世废土": ["拼贴构成", "铜版木刻", "丝网波普", "钢笔线描", "黑白漫画", "档案拼贴"],
    "悬疑推理": ["铜版木刻", "古籍绣像", "民国画报", "钢笔线描", "水彩淡彩", "新艺术装饰", "黑白漫画", "档案拼贴"],
    "现代都市": ["水彩淡彩", "扁平极简", "蜡笔色粉"],
    "校园日常": ["蜡笔色粉", "复古绘本", "水彩淡彩"],
    "奇幻童话": ["复古绘本", "新艺术装饰", "水彩淡彩", "蜡笔色粉"],
    "恐怖诡秘": ["新艺术装饰", "铜版木刻", "钢笔线描", "黑白漫画", "档案拼贴"],
    "其他": ["水彩淡彩", "钢笔线描", "扁平极简", "水墨写意", "黑白漫画"],
}


def _hash_int(seed: str) -> int:
    return int(hashlib.md5((seed or "").encode("utf-8")).hexdigest(), 16)


def _normalized_style_scores(raw_scores: Any, culture: str | None) -> dict[str, float]:
    """Parse LLM style_scores into a whitelist/culture-filtered score map."""
    if not isinstance(raw_scores, list):
        return {}
    scores: dict[str, float] = {}
    for item in raw_scores:
        if not isinstance(item, dict):
            continue
        style = (item.get("style") or "").strip()
        if not style_allowed_for_culture(style, culture):
            continue
        try:
            score = float(item.get("score", 0))
        except (TypeError, ValueError):
            continue
        if score <= 0:
            continue
        scores[style] = max(scores.get(style, 0.0), min(score, 1.0))
    return scores


def _deterministic_weighted_pick(
    weighted_candidates: list[tuple[str, float]], seed: str
) -> str:
    """Pick deterministically. Equal weights preserve the old modulo behavior."""
    if not weighted_candidates:
        return ART_STYLE_FALLBACK
    styles = [s for s, _ in weighted_candidates]
    weights = [max(w, 0.01) for _, w in weighted_candidates]
    if len({round(w, 6) for w in weights}) == 1:
        return styles[_hash_int(seed) % len(styles)]
    total = sum(weights)
    bucket = (_hash_int(seed) % 1_000_000) / 1_000_000 * total
    cursor = 0.0
    for style, weight in zip(styles, weights):
        cursor += max(weight, 0.01)
        if bucket < cursor:
            return style
    return styles[-1]


def filtered_style_pool(genre_category: str | None, culture: str | None = None) -> list[str]:
    """Return the genre pool after culture hard filtering, with safe fallback."""
    pool = GENRE_STYLE_POOL.get((genre_category or "").strip()) or GENRE_STYLE_POOL["其他"]
    filtered = [style for style in pool if style_allowed_for_culture(style, culture)]
    if filtered:
        return filtered
    if culture and culture in CULTURE_CATEGORIES:
        culture_fallback = [
            style
            for style in GENRE_STYLE_POOL["其他"]
            if style_allowed_for_culture(style, culture)
        ]
        if culture_fallback:
            return culture_fallback
    return [ART_STYLE_FALLBACK]


def pick_art_style(
    genre_category: str | None,
    world_name: str,
    *,
    culture: str | None = None,
    style_scores: Any = None,
) -> str:
    """Pick a 画法 by culture-filtered genre pool + deterministic weighted hash.

    Deterministic (same world → same style across regens), and spreads
    same-genre worlds across the pool instead of all collapsing on one style.
    LLM ``style_scores`` may weight valid in-pool styles and add at most two
    high-confidence culture-safe surprise styles; it never bypasses whitelist
    or culture filtering.
    """
    pool = filtered_style_pool(genre_category, culture)
    score_map = _normalized_style_scores(style_scores, culture)
    candidates = list(pool)

    # Aggressive, but gated: allow at most two high-confidence LLM picks outside
    # the base genre pool if they are whitelisted and culture-compatible.
    for style, score in sorted(score_map.items(), key=lambda item: item[1], reverse=True):
        if style in candidates:
            continue
        if score < 0.82:
            continue
        candidates.append(style)
        if len(candidates) >= len(pool) + 2:
            break

    weighted: list[tuple[str, float]] = []
    for style in candidates:
        score = score_map.get(style)
        if score is not None and score < 0.28 and len(candidates) > 2:
            continue
        weighted.append((style, 0.35 + score if score is not None else 0.75))
    if not weighted:
        weighted = [(style, 1.0) for style in pool]
    return _deterministic_weighted_pick(weighted, world_name)


def visual_style_snapshot(brief: CoverBrief, *, style_scores: Any = None) -> dict[str, Any]:
    """Small JSON payload persisted on drafts/world lore for visual consistency."""
    snapshot: dict[str, Any] = {
        "version": 1,
        "genre_category": brief.genre_category,
        "culture": brief.culture,
        "art_style": brief.art_style,
    }
    scores = _normalized_style_scores(
        style_scores if style_scores is not None else brief.style_scores,
        brief.culture,
    )
    if scores:
        snapshot["style_scores"] = [
            {"style": style, "score": score}
            for style, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
        ]
    return snapshot


def persisted_visual_style_from_world_data(world_data: dict[str, Any]) -> dict[str, Any]:
    """Read a saved visual_style from draft payload or published world lore_pack."""
    direct = world_data.get("visual_style")
    if isinstance(direct, dict):
        return direct
    lore_pack = world_data.get("lore_pack")
    if isinstance(lore_pack, dict) and isinstance(lore_pack.get("visual_style"), dict):
        return lore_pack["visual_style"]
    return {}


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


def _deip_descriptor(char: CharacterCoverBrief) -> str:
    """De-IP'd descriptor for the ip_fallback tier: prefer the LLM-written
    ``deip_hint`` (rich, trademark-free look), else the 4-dim fallback."""
    hint = (char.deip_hint or "").strip()
    if hint:
        return f"{hint}；{char.mood_anchor}" if char.mood_anchor else hint
    return _character_descriptor(char)


def build_character_portrait_prompt(
    world_brief: CoverBrief, char: CharacterCoverBrief, ip_fallback: bool = False
) -> str:
    """2:3 character portrait in the world's 画法. Unlike covers, portraits keep
    a hard "clear face on the upper third" constraint for the front-end's
    circular avatar crop — so the 画法 styles the face but must not abstract it
    away (no pure silhouette / faceless collage).

    ``ip_fallback`` (for IP worlds whose direct portrait is moderation-blocked on
    与第三方内容相似性): drop the IP world name + canonical character name + the
    "保留原作" fidelity clause, and paint a trademark-free ORIGINAL character from
    ``deip_hint``. Empirically this passes the upstream image guard while keeping
    the character on-vibe. The most trademark-defined identifiers (e.g. a signature
    accessory) are intentionally softened away by the deip_hint author."""
    face_and_style = (
        f"画法：{resolve_style_desc(world_brief.art_style)}"
        "用这种画法的笔触与肌理塑造人物，但人物要有清晰可辨的面部、半身或胸像构图，"
        "眼线落在画面上三分位附近（前端将自动裁出圆形头像）；不要纯剪影或抹去五官。"
        "不要照相写实渲染、塑料皮肤或过度磨皮。"
    )
    tail = (
        "画面中不要出现任何文字、姓名标签或字幕。"
        f"{_WEB_LEGIBILITY}"
        f"{_LOGO_NEGATIVE}"
        "2:3 竖版。"
    )
    if ip_fallback:
        return (
            f"创作一幅 2:3 人物主视觉：{_deip_descriptor(char)}。"
            f"{face_and_style}"
            "请把 ta 当作一个全新的原创角色来刻画，不要复刻任何已知影视或文学作品里的"
            "官方造型、演员相貌、商标或标识。"
            f"{tail}"
        )
    return (
        f"为《{world_brief.world_name}》中的角色「{char.name}」（{_character_descriptor(char)}）创作一幅 2:3 人物主视觉。"
        f"{face_and_style}"
        f"{_fidelity_clause(world_brief)}"
        f"{tail}"
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
    "STYLE_CULTURE_TAGS",
    "CULTURE_CATEGORIES",
    "resolve_style_desc",
    "style_allowed_for_culture",
    "filtered_style_pool",
    "pick_art_style",
    "visual_style_snapshot",
    "persisted_visual_style_from_world_data",
    "IP_NAME_CONFIDENCE_FLOOR",
    "derive_character_reference_anchor",
    "build_world_hero_prompt",
    "build_world_cover_prompt",
    "build_script_cover_prompt",
    "build_character_portrait_prompt",
    "build_ending_card_prompt",
]
