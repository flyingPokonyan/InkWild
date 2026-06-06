"""Extract repeated imagery phrases from recent narrator outputs.

BUGS #27 update 4 hardcoded a 唐风 list (烛火/光柱/尘埃/更漏) into the
narrator prompt. Other worlds (sci-fi, victorian, modern) don't trigger
those tokens so the dedup signal is dead. This module replaces the static
list with a frequency-based extractor over the past N narrator segments —
content-agnostic, just bigrams of Chinese chars filtered against a tiny
stopword set.

Imagery is overwhelmingly 2-char compounds (烛火, 光柱, 尘埃, 长廊, 雾气,
血迹, 银光, 残月). Catching repeated bigrams across 2 segments is a
reasonable proxy without needing per-world dictionaries.
"""
from __future__ import annotations

import re
from collections import Counter

# Bigrams composed of only CJK ideographs.
_CJK_RE = re.compile(r"[一-鿿]")

# Pronouns / particles / common verbs — short tail; we only need to avoid
# the very loudest false positives. The bigram itself filters most noise.
_STOPWORD_BIGRAMS: frozenset[str] = frozenset({
    "他们", "她们", "你们", "我们", "自己", "什么", "怎么", "这个", "那个",
    "这是", "那是", "就是", "还是", "不是", "已经", "正在", "刚刚", "马上",
    "现在", "刚才", "之后", "然后", "突然", "忽然", "终于", "可是", "但是",
    "于是", "因为", "所以", "如果", "虽然", "并不", "只是", "也是", "或许",
    "确实", "似乎", "仿佛", "好像", "应该", "可能", "必须", "只有",
})


def _extract_cjk_bigrams(text: str) -> list[str]:
    """Sliding-window bigrams over CJK-only character runs.

    Mixed-language stretches are split on the first non-CJK char so we
    don't get spurious bigrams that straddle Latin punctuation.
    """
    bigrams: list[str] = []
    run: list[str] = []
    for ch in text:
        if _CJK_RE.match(ch):
            run.append(ch)
        else:
            if len(run) >= 2:
                for i in range(len(run) - 1):
                    bigrams.append(run[i] + run[i + 1])
            run = []
    if len(run) >= 2:
        for i in range(len(run) - 1):
            bigrams.append(run[i] + run[i + 1])
    return bigrams


def extract_repeated_imagery(
    segments: list[str],
    *,
    min_count: int = 2,
    max_items: int = 8,
    skip_names: set[str] | None = None,
) -> list[str]:
    """Return up to *max_items* bigrams that appear ≥ *min_count* times.

    ``skip_names`` is the set of in-world NPC / place names; bigrams that
    match an NPC name shouldn't be flagged as "don't repeat" — narrator
    rightly mentions them across turns.

    Ordering: by frequency desc, then by first-seen order for stable output.
    """
    if not segments:
        return []
    skip = {n.strip() for n in (skip_names or set()) if n and len(n) >= 2}
    counter: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for seg in segments:
        if not seg:
            continue
        for idx, bg in enumerate(_extract_cjk_bigrams(seg)):
            if bg in _STOPWORD_BIGRAMS:
                continue
            # Skip bigrams that are substrings of any skip name (catches
            # 福尔 from 福尔摩斯, 雷斯 from 雷斯垂德, etc).
            if any(bg in name for name in skip):
                continue
            counter[bg] += 1
            first_seen.setdefault(bg, idx)
    repeated = [bg for bg, n in counter.items() if n >= min_count]
    repeated.sort(key=lambda bg: (-counter[bg], first_seen[bg]))
    return repeated[:max_items]


__all__ = ["extract_repeated_imagery"]
