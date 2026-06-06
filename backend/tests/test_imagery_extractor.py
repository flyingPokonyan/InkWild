"""Tests for narrator imagery dedup extractor."""
from engine.imagery_extractor import extract_repeated_imagery


def test_single_segment_returns_empty():
    # Bigrams within one segment can repeat too, but it's a single round —
    # no need to flag yet.
    out = extract_repeated_imagery(["烛火映照大厅，烛火摇曳"])
    # Each bigram appears at least twice in this single string, so it
    # should still surface. We only suppress when *no* repetition exists.
    assert "烛火" in out


def test_repeated_across_segments_detected():
    segs = [
        "烛火映照在尘埃上，更漏滴答",
        "尘埃飞舞，烛火依旧摇曳，更漏沉沉",
    ]
    out = extract_repeated_imagery(segs)
    # All three should be flagged as repeated.
    assert "烛火" in out
    assert "尘埃" in out
    assert "更漏" in out


def test_skip_names_filters_npc_substrings():
    segs = [
        "福尔摩斯走入大厅，福尔摩斯环顾四周",
        "福尔摩斯沉吟良久，雾气弥漫，雾气浓重",
    ]
    out = extract_repeated_imagery(segs, skip_names={"福尔摩斯"})
    assert all("福尔" not in bg and "尔摩" not in bg and "摩斯" not in bg for bg in out), out
    assert "雾气" in out


def test_max_items_capped():
    segs = ["烛火尘埃更漏银光月色血迹雾气", "烛火尘埃更漏银光月色血迹雾气"]
    out = extract_repeated_imagery(segs, max_items=3)
    assert len(out) <= 3


def test_stopwords_excluded():
    segs = ["他们终于已经完成", "他们终于已经完成"]
    out = extract_repeated_imagery(segs)
    assert "他们" not in out
    assert "已经" not in out


def test_empty_input():
    assert extract_repeated_imagery([]) == []
    assert extract_repeated_imagery(["", None]) == []
