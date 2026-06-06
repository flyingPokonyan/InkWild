import pytest
from unittest.mock import AsyncMock

from services.world_moderation_service import (
    moderate_world_payload,
    extract_moderation_flags,
)


@pytest.mark.asyncio
async def test_no_flags_returns_empty():
    fake = AsyncMock(return_value={"flagged": False, "reasons": []})
    payload = {
        "world_characters": [{"name": "A", "personality": "和善", "secret": ""}],
        "shared_events": [{"id": "e1", "summary": "正常事件"}],
        "events_data": [{"id": "ev1", "summary": "推进剧情"}],
        "lore_pack": {"dimensions": [{"key": "x", "content_blocks": [{"heading": "h", "body": "b"}]}]},
    }
    warnings = await moderate_world_payload(payload, fake)
    assert warnings == []


@pytest.mark.asyncio
async def test_flagged_personality_yields_warning():
    async def callable_(text):
        return {"flagged": "暴力" in text, "reasons": ["violence"] if "暴力" in text else []}
    payload = {"world_characters": [{"name": "A", "personality": "暴力倾向", "secret": ""}]}
    warnings = await moderate_world_payload(payload, callable_)
    assert any("moderation_flag:violence" in w for w in warnings)


@pytest.mark.asyncio
async def test_flagged_lore_block_yields_warning():
    async def callable_(text):
        flagged = "禁忌" in text
        return {"flagged": flagged, "reasons": ["sensitive"] if flagged else []}
    payload = {"lore_pack": {"dimensions": [
        {"key": "x", "content_blocks": [{"heading": "h", "body": "禁忌内容描述"}]},
    ]}}
    warnings = await moderate_world_payload(payload, callable_)
    assert any("moderation_flag:sensitive" in w for w in warnings)


@pytest.mark.asyncio
async def test_sample_limit_applied():
    """超过 sample_passages 数量的字段不再调 moderation。"""
    calls = []

    async def callable_(text):
        calls.append(text)
        return {"flagged": False, "reasons": []}

    payload = {"world_characters": [
        {"name": f"N{i}", "personality": f"p{i}", "secret": f"s{i}"} for i in range(20)
    ]}
    warnings = await moderate_world_payload(payload, callable_, sample_passages=3)
    # 每类取前 3 条：3 personality + 3 secret = 6 calls
    assert len(calls) <= 6


@pytest.mark.asyncio
async def test_moderation_failure_does_not_raise():
    """moderation_callable 抛错不应阻断，记录 warning 即可。"""
    async def boom(text):
        raise RuntimeError("API down")

    payload = {"world_characters": [{"name": "A", "personality": "p", "secret": ""}]}
    warnings = await moderate_world_payload(payload, boom)
    # 不抛错；可能产生空 warning 或 internal_error warning
    assert isinstance(warnings, list)


def test_extract_moderation_flags():
    quality_warnings = [
        "shape_violation: x",
        "moderation_flag:violence",
        "moderation_flag:sensitive",
        "other_warning",
    ]
    flags = extract_moderation_flags(quality_warnings)
    assert flags == ["violence", "sensitive"]


def test_extract_moderation_flags_empty():
    assert extract_moderation_flags([]) == []
    assert extract_moderation_flags(["shape_violation: x", "other"]) == []


def test_extract_moderation_flags_handles_dedup():
    """同一 reason 重复的话保留全部（不去重 — admin 看到次数有意义）。"""
    flags = extract_moderation_flags(["moderation_flag:violence", "moderation_flag:violence"])
    assert flags == ["violence", "violence"]
