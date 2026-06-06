"""Aspect ratio → size mapping tests for Seedream-compatible providers."""
from llm.openai_compatible import _size_for_aspect_ratio


def test_legacy_ratios_unchanged():
    assert _size_for_aspect_ratio("1:1") == "1024x1024"
    assert _size_for_aspect_ratio("16:9") == "1536x1024"
    assert _size_for_aspect_ratio("3:4") == "1024x1536"
    assert _size_for_aspect_ratio("4:3") == "1536x1024"


def test_new_ratios_supported():
    # 21:9 super-wide hero — width-dominant
    out = _size_for_aspect_ratio("21:9")
    w, h = (int(x) for x in out.split("x"))
    assert w > h
    assert abs((w / h) - (21 / 9)) < 0.05

    # 3:2 cinematic horizontal card
    out = _size_for_aspect_ratio("3:2")
    w, h = (int(x) for x in out.split("x"))
    assert w > h
    assert abs((w / h) - 1.5) < 0.05

    # 2:3 vertical portrait
    out = _size_for_aspect_ratio("2:3")
    w, h = (int(x) for x in out.split("x"))
    assert h > w
    assert abs((w / h) - (2 / 3)) < 0.05


def test_unknown_falls_back_to_square():
    assert _size_for_aspect_ratio("nonsense") == "1024x1024"
