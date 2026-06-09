from engine.compressor import (
    build_compression_prompt,
    claim_compression_round,
    merge_context_summary,
    should_compress,
)


def test_should_compress_when_threshold_reached():
    assert should_compress(rounds_played=22, last_compressed_round=0, threshold=20)


def test_should_not_compress_below_threshold():
    assert not should_compress(rounds_played=15, last_compressed_round=0, threshold=20)


def test_should_not_compress_too_soon_after_last():
    assert not should_compress(rounds_played=23, last_compressed_round=20, threshold=20)


def test_should_compress_after_gap():
    # MIN_GAP is 10: a gap of 8 is still too soon, 10 is due.
    assert not should_compress(rounds_played=28, last_compressed_round=20, threshold=20)
    assert should_compress(rounds_played=30, last_compressed_round=20, threshold=20)


def test_claim_compression_returns_stamp_when_due():
    # First eligible round past threshold returns the round to stamp as the
    # new last_compressed_round (the debounce marker the caller persists).
    assert claim_compression_round(22, 0, threshold=20) == 22


def test_claim_compression_returns_none_before_threshold():
    assert claim_compression_round(15, 0, threshold=20) is None


def test_claim_compression_debounces_within_gap():
    # Just stamped at round 22 — the next few rounds are within MIN_GAP and
    # must NOT re-fire. This is the regression guard: the old code never
    # advanced the stamp, so compression re-fired every round past threshold.
    assert claim_compression_round(27, 22, threshold=20) is None  # gap 5 < 10
    assert claim_compression_round(31, 22, threshold=20) is None  # gap 9 < 10
    # Exactly MIN_GAP (10) rounds later it is due again.
    assert claim_compression_round(32, 22, threshold=20) == 32


def test_merge_context_summary_appends_new_segment():
    out = merge_context_summary(None, "第一段摘要")
    assert "第一段摘要" in out


def test_merge_context_summary_caps_to_recent_segments():
    # The running summary sits in the per-turn prompt tail and is never
    # prefix-cached; unbounded append inflates every Director call. Keep only
    # the most recent N segments.
    summary = None
    for i in range(10):
        summary = merge_context_summary(summary, f"段{i}", max_segments=6)
    assert "段9" in summary
    assert "段4" in summary  # last 6 == 段4..段9
    assert "段3" not in summary
    assert "段0" not in summary


def test_compression_prompt():
    messages = [
        {"role": "user", "content": "我去茶摊"},
        {"role": "assistant", "content": "你走到茶摊，老板热情招呼你。"},
        {"role": "user", "content": "问老板关于失踪的事"},
        {"role": "assistant", "content": "老板神色一变，压低声音说：'别问了，问多了对你不好。'"},
    ]

    prompt = build_compression_prompt(messages)

    assert "茶摊" in prompt
    assert "失踪" in prompt
