"""UsageContext + usage_recorder behavioral tests.

Three things must hold for the AOP token-recording approach to work:

1. ``usage_context`` propagates across ``await``, ``asyncio.create_task``,
   and ``asyncio.gather`` (otherwise NPC concurrency / reflection /
   parallel workshop stages lose attribution).
2. Nested ``usage_context`` blocks merge with the parent (so a sub-stage
   can override ``phase`` without re-stating session/task identity).
3. ``record_text_usage`` / ``record_image_usage`` are best-effort: any
   internal failure is swallowed.
"""

from __future__ import annotations

import asyncio

import pytest

from llm.usage_context import (
    UsageContext,
    current_usage_context,
    usage_context,
)
from services import usage_recorder


@pytest.mark.asyncio
async def test_context_default_is_none() -> None:
    assert current_usage_context() is None


@pytest.mark.asyncio
async def test_context_set_and_reset() -> None:
    with usage_context(purpose="game", session_id="s1"):
        ctx = current_usage_context()
        assert ctx is not None
        assert ctx.purpose == "game"
        assert ctx.session_id == "s1"
    assert current_usage_context() is None


@pytest.mark.asyncio
async def test_context_propagates_to_created_task() -> None:
    seen: list[UsageContext | None] = []

    async def child() -> None:
        seen.append(current_usage_context())

    with usage_context(purpose="world_gen", task_id="t1", user_id="u1"):
        await asyncio.create_task(child())

    assert len(seen) == 1
    assert seen[0] is not None
    assert seen[0].purpose == "world_gen"
    assert seen[0].task_id == "t1"
    assert seen[0].user_id == "u1"


@pytest.mark.asyncio
async def test_context_propagates_across_gather() -> None:
    seen: list[UsageContext | None] = []

    async def worker(_i: int) -> None:
        await asyncio.sleep(0)
        seen.append(current_usage_context())

    with usage_context(purpose="game", session_id="s2"):
        await asyncio.gather(*(worker(i) for i in range(3)))

    assert len(seen) == 3
    for ctx in seen:
        assert ctx is not None
        assert ctx.session_id == "s2"


@pytest.mark.asyncio
async def test_nested_context_inherits_identity_overrides_phase() -> None:
    with usage_context(purpose="world_gen", task_id="t1", user_id="u1"):
        with usage_context(phase="world_gen.research"):
            ctx = current_usage_context()
            assert ctx is not None
            assert ctx.purpose == "world_gen"
            assert ctx.task_id == "t1"
            assert ctx.user_id == "u1"
            assert ctx.phase == "world_gen.research"
        # phase falls back after inner block exits
        outer = current_usage_context()
        assert outer is not None
        assert outer.phase is None


@pytest.mark.asyncio
async def test_nested_context_can_override_identity() -> None:
    with usage_context(purpose="game", session_id="s1"):
        with usage_context(purpose="reflection", session_id="s2"):
            ctx = current_usage_context()
            assert ctx is not None
            assert ctx.purpose == "reflection"
            assert ctx.session_id == "s2"
        outer = current_usage_context()
        assert outer is not None
        assert outer.purpose == "game"
        assert outer.session_id == "s1"


@pytest.mark.asyncio
async def test_record_text_usage_swallows_invalid_purpose(caplog) -> None:
    # Purpose outside the allowed set is dropped silently with a log.
    ctx = UsageContext(purpose="not_a_real_purpose", session_id="s1")
    await usage_recorder.record_text_usage(
        {"type": "usage", "input_tokens": 10, "output_tokens": 5},
        ctx,
    )  # must not raise


@pytest.mark.asyncio
async def test_record_text_usage_swallows_missing_identity() -> None:
    # purpose set but no session_id nor task_id → drop silently.
    ctx = UsageContext(purpose="game")
    await usage_recorder.record_text_usage(
        {"type": "usage", "input_tokens": 10, "output_tokens": 5},
        ctx,
    )  # must not raise


@pytest.mark.asyncio
async def test_record_text_usage_swallows_db_failure(monkeypatch) -> None:
    # If pricing_lookup or db blows up, the recorder must still not raise.
    async def boom(*args, **kwargs):
        raise RuntimeError("simulated db failure")

    monkeypatch.setattr(usage_recorder, "get_pricing_for", boom)
    ctx = UsageContext(purpose="game", session_id="s1")
    await usage_recorder.record_text_usage(
        {"type": "usage", "input_tokens": 10, "output_tokens": 5},
        ctx,
    )  # must not raise


@pytest.mark.asyncio
async def test_record_image_usage_swallows_invalid_purpose() -> None:
    ctx = UsageContext(purpose="bad", task_id="t1")
    await usage_recorder.record_image_usage(
        provider_name="seedream",
        model_id="seedream-1.0",
        ctx=ctx,
        count=1,
    )  # must not raise


@pytest.mark.asyncio
async def test_record_image_usage_skips_zero_count() -> None:
    ctx = UsageContext(purpose="image_gen", task_id="t1")
    await usage_recorder.record_image_usage(
        provider_name="seedream",
        model_id="seedream-1.0",
        ctx=ctx,
        count=0,
    )  # must not raise — but also must not insert


@pytest.mark.asyncio
async def test_record_text_usage_persists_cache_tokens(
    monkeypatch, test_session_factory
) -> None:
    """DeepSeek-style prefix-cache hit/miss from the usage event must be
    persisted onto the token_usage row (not just logged)."""
    from sqlalchemy import select

    from models.game import TokenUsage

    async def _no_pricing(*_args, **_kwargs):
        return None

    monkeypatch.setattr(usage_recorder, "async_session", test_session_factory)
    monkeypatch.setattr(usage_recorder, "get_pricing_for", _no_pricing)

    await usage_recorder.record_text_usage(
        {
            "type": "usage",
            "input_tokens": 100,
            "output_tokens": 25,
            "cache_hit_tokens": 80,
            "cache_miss_tokens": 20,
            "provider_name": "DeepSeek",
            "model_id": "deepseek-v4",
        },
        UsageContext(purpose="game", session_id="00000000-0000-0000-0000-0000000000a1", phase="director"),
    )

    async with test_session_factory() as db:
        row = (
            await db.execute(
                select(TokenUsage).where(TokenUsage.session_id == "00000000-0000-0000-0000-0000000000a1")
            )
        ).scalar_one()

    assert row.cache_hit_tokens == 80
    assert row.cache_miss_tokens == 20
    # phase already exists on the model — assert it rides along so the
    # per-stage measurement query can group by it.
    assert row.phase == "director"
    assert row.input_tokens == 100


@pytest.mark.asyncio
async def test_record_text_usage_leaves_cache_null_when_unsupported(
    monkeypatch, test_session_factory
) -> None:
    """Providers that don't report cache tokens (no cache_* keys in the
    event) leave the columns NULL — distinct from a reported zero."""
    from sqlalchemy import select

    from models.game import TokenUsage

    async def _no_pricing(*_args, **_kwargs):
        return None

    monkeypatch.setattr(usage_recorder, "async_session", test_session_factory)
    monkeypatch.setattr(usage_recorder, "get_pricing_for", _no_pricing)

    await usage_recorder.record_text_usage(
        {"type": "usage", "input_tokens": 10, "output_tokens": 5},
        UsageContext(purpose="game", session_id="00000000-0000-0000-0000-0000000000a2"),
    )

    async with test_session_factory() as db:
        row = (
            await db.execute(
                select(TokenUsage).where(TokenUsage.session_id == "00000000-0000-0000-0000-0000000000a2")
            )
        ).scalar_one()

    assert row.cache_hit_tokens is None
    assert row.cache_miss_tokens is None
