"""Tests for heavy_critic_characters and heavy_critic_playable."""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock

from services.world_critic_service import (
    heavy_critic_characters,
    heavy_critic_playable,
)


def _make_router(responses: list[str]):
    """Return a fake llm_router that yields text_delta events for each call in sequence."""
    fake = MagicMock()
    idx = {"n": 0}

    async def stream(*, messages, tools=None, system, max_tokens):
        i = idx["n"]
        idx["n"] += 1
        text = responses[i] if i < len(responses) else "{}"
        yield {"type": "text_delta", "text": text}

    fake.stream_with_tools = stream
    fake._calls = idx
    return fake


# ---- heavy_critic_characters ----

@pytest.mark.asyncio
async def test_heavy_critic_no_issues_returns_unchanged():
    chars = [{"name": "A", "personality": "p", "secret": "s", "knowledge": []}]
    router = _make_router([json.dumps({"verdict": "ok", "issues": []})])

    updated, warnings = await heavy_critic_characters(chars, "desc", {}, router)
    assert updated == chars
    assert warnings == []


@pytest.mark.asyncio
async def test_heavy_critic_needs_repair_calls_repair_pass():
    chars = [{"name": "A", "personality": "和善", "secret": "暗杀别人", "knowledge": []}]

    critic_resp = json.dumps({
        "verdict": "needs_repair",
        "issues": [{"target": "A", "kind": "personality_secret_conflict", "detail": "personality 跟 secret 矛盾"}],
    })
    repair_resp = json.dumps({"characters": [{"name": "A", "personality": "表面和善实则心狠", "secret": "暗杀别人", "knowledge": []}]})
    final_critic_resp = json.dumps({"verdict": "ok", "issues": []})

    router = _make_router([critic_resp, repair_resp, final_critic_resp])

    updated, warnings = await heavy_critic_characters(chars, "desc", {}, router)
    by_name = {c["name"]: c for c in updated}
    assert "A" in by_name
    assert "心狠" in by_name["A"]["personality"]
    assert warnings == []  # 修复成功，无 lingering warnings


@pytest.mark.asyncio
async def test_heavy_critic_repair_keeps_name():
    """repair 时 character.name 不应被修改（保护下游引用）"""
    chars = [{"name": "OriginalName", "personality": "p", "secret": "矛盾"}]
    critic_resp = json.dumps({"verdict": "needs_repair", "issues": [{"target": "OriginalName", "kind": "x", "detail": "x"}]})
    # LLM 错把 name 改了，本函数应忽略改名（只 by name 匹配）
    repair_resp = json.dumps({"characters": [{"name": "RenamedByLLM", "personality": "fixed", "secret": "fixed"}]})
    final_critic_resp = json.dumps({"verdict": "ok", "issues": []})

    router = _make_router([critic_resp, repair_resp, final_critic_resp])
    updated, warnings = await heavy_critic_characters(chars, "desc", {}, router)

    # OriginalName 仍在；不接受改名
    names = {c["name"] for c in updated}
    assert "OriginalName" in names
    assert "RenamedByLLM" not in names


@pytest.mark.asyncio
async def test_heavy_critic_unfixed_issues_warned():
    """修复后仍有 issues → 标 quality_warnings 不抛错。"""
    chars = [{"name": "A", "personality": "p", "secret": "s"}]
    critic1 = json.dumps({"verdict": "needs_repair", "issues": [{"target": "A", "kind": "x", "detail": "y"}]})
    repair = json.dumps({"characters": [{"name": "A", "personality": "p2", "secret": "s2"}]})
    critic2 = json.dumps({"verdict": "needs_repair", "issues": [{"target": "A", "kind": "still_bad", "detail": "still bad"}]})

    router = _make_router([critic1, repair, critic2])
    updated, warnings = await heavy_critic_characters(chars, "desc", {}, router)

    assert any("heavy_critic" in w and "still_bad" in w for w in warnings)


@pytest.mark.asyncio
async def test_heavy_critic_llm_failure_returns_unchanged():
    chars = [{"name": "A", "personality": "p"}]
    fake = MagicMock()

    async def boom(**kw):
        raise RuntimeError("LLM 5xx")
        yield  # make it an async generator

    fake.stream_with_tools = boom

    updated, warnings = await heavy_critic_characters(chars, "desc", {}, fake)
    assert updated == chars
    assert warnings == []  # LLM 挂了不阻塞


@pytest.mark.asyncio
async def test_heavy_critic_invalid_json_returns_unchanged():
    chars = [{"name": "A", "personality": "p"}]
    router = _make_router(["not json"])
    updated, warnings = await heavy_critic_characters(chars, "desc", {}, router)
    assert updated == chars


@pytest.mark.asyncio
async def test_heavy_critic_repair_disabled_skips_repair():
    """allow_repair=False 时仅 critic 不修复"""
    chars = [{"name": "A", "personality": "p", "secret": "s"}]
    critic = json.dumps({"verdict": "needs_repair", "issues": [{"target": "A", "kind": "x", "detail": "y"}]})
    router = _make_router([critic])

    updated, warnings = await heavy_critic_characters(chars, "desc", {}, router, allow_repair=False)
    assert updated == chars  # 没 repair
    assert any("heavy_critic" in w for w in warnings)


@pytest.mark.asyncio
async def test_heavy_critic_empty_characters_returns_immediately():
    """空 characters 直接返回，不调 LLM。"""
    fake = MagicMock()
    call_count = {"n": 0}

    async def should_not_call(**kw):
        call_count["n"] += 1
        yield {"type": "text_delta", "text": "{}"}

    fake.stream_with_tools = should_not_call
    updated, warnings = await heavy_critic_characters([], "desc", {}, fake)
    assert updated == []
    assert warnings == []
    assert call_count["n"] == 0


@pytest.mark.asyncio
async def test_heavy_critic_name_protected_on_repaired_char():
    """即使 repair LLM 保持了正确 name，repaired 版本的其他字段应被合并。"""
    chars = [{"name": "Bob", "personality": "cold", "secret": "bad"}]
    critic_resp = json.dumps({
        "verdict": "needs_repair",
        "issues": [{"target": "Bob", "kind": "personality_secret_conflict", "detail": "conflict"}],
    })
    repair_resp = json.dumps({"characters": [{"name": "Bob", "personality": "warm inside", "secret": "bad"}]})
    final_critic_resp = json.dumps({"verdict": "ok", "issues": []})

    router = _make_router([critic_resp, repair_resp, final_critic_resp])
    updated, warnings = await heavy_critic_characters(chars, "desc", {}, router)

    by_name = {c["name"]: c for c in updated}
    assert "Bob" in by_name
    assert "warm" in by_name["Bob"]["personality"]  # repaired field applied
    assert by_name["Bob"]["name"] == "Bob"


# ---- heavy_critic_playable ----

@pytest.mark.asyncio
async def test_heavy_critic_playable_clean():
    pl = [{"name": "A", "role_tag": "主角"}]
    chars = [{"name": "A"}]
    router = _make_router([json.dumps({"warnings": []})])
    updated, warns = await heavy_critic_playable(pl, chars, router)
    assert updated == pl
    assert warns == []


@pytest.mark.asyncio
async def test_heavy_critic_playable_warns():
    pl = [{"name": "Ghost", "role_tag": "主角"}]
    chars = [{"name": "A"}]
    router = _make_router([json.dumps({"warnings": ["Ghost 不在 characters 里"]})])
    updated, warns = await heavy_critic_playable(pl, chars, router)
    assert "Ghost" in warns[0]


@pytest.mark.asyncio
async def test_heavy_critic_playable_llm_failure_returns_unchanged():
    pl = [{"name": "A", "role_tag": "主角"}]
    chars = [{"name": "A"}]
    fake = MagicMock()

    async def boom(**kw):
        raise RuntimeError("LLM down")
        yield

    fake.stream_with_tools = boom
    updated, warns = await heavy_critic_playable(pl, chars, fake)
    assert updated == pl
    assert warns == []


@pytest.mark.asyncio
async def test_heavy_critic_playable_empty_returns_unchanged():
    """空 playable 直接返回，不调 LLM。"""
    fake = MagicMock()
    call_count = {"n": 0}

    async def should_not_call(**kw):
        call_count["n"] += 1
        yield {"type": "text_delta", "text": "{}"}

    fake.stream_with_tools = should_not_call
    updated, warns = await heavy_critic_playable([], [], fake)
    assert updated == []
    assert warns == []
    assert call_count["n"] == 0
