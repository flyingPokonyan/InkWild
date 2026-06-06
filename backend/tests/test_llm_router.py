import asyncio
import time

import pytest

from llm.base import LLMProvider
from llm.router import LLMRouter, _is_transient


class FakeProvider(LLMProvider):
    def __init__(self, response_text: str):
        self.response_text = response_text

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048, response_format=None):
        yield {"type": "text_delta", "text": self.response_text}
        yield {
            "type": "tool_use",
            "name": "update_game_state",
            "input": {"time_advance": False, "quick_actions": ["看看"]},
        }
        yield {"type": "usage", "input_tokens": 100, "output_tokens": 50}


class FailingProvider(LLMProvider):
    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048, response_format=None):
        if False:
            yield {}
        raise Exception("down")


@pytest.mark.asyncio
async def test_router_selects_provider():
    provider = FakeProvider("你好")
    router = LLMRouter(providers={"fake": provider})

    events = []
    async for event in router.stream_with_tools([], [], provider_name="fake"):
        events.append(event)

    assert len(events) == 3
    assert events[0]["type"] == "text_delta"
    assert events[0]["text"] == "你好"
    assert events[1]["type"] == "tool_use"


@pytest.mark.asyncio
async def test_router_fallback():
    failing = FailingProvider()
    backup = FakeProvider("降级回复")

    router = LLMRouter(
        providers={"primary": failing, "backup": backup},
        fallback_chain=["primary", "backup"],
    )

    events = []
    async for event in router.stream_with_tools([], [], provider_name="primary"):
        events.append(event)

    assert any(event.get("text") == "降级回复" for event in events)


# Phase 2.B.1 — timeout / retry tests --------------------------------------


class HangingProvider(LLMProvider):
    """Never yields anything; lets us verify first-token timeout."""

    def __init__(self) -> None:
        self.call_count = 0

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048, response_format=None):
        self.call_count += 1
        await asyncio.sleep(10)  # well beyond test timeout
        if False:
            yield {}


class TransientThenOKProvider(LLMProvider):
    """First call raises a transient error; second call succeeds."""

    def __init__(self) -> None:
        self.call_count = 0

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048, response_format=None):
        self.call_count += 1
        if self.call_count == 1:
            raise APITimeoutError("transient")
        yield {"type": "text_delta", "text": "重试成功"}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}


class APITimeoutError(Exception):
    """Mimics openai.APITimeoutError by class name only."""


class AuthError(Exception):
    """Non-transient: auth failures should NOT retry."""

    status_code = 401


@pytest.mark.asyncio
async def test_router_first_token_timeout_falls_back_after_retries():
    hanging = HangingProvider()
    backup = FakeProvider("救场")
    router = LLMRouter(
        providers={"slow": hanging, "backup": backup},
        fallback_chain=["slow", "backup"],
        timeout_seconds=0.05,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    events: list[dict] = []
    async for event in router.stream_with_tools([], [], provider_name="slow"):
        events.append(event)

    # 1 attempt + 1 retry = 2 calls into hanging provider before fallback.
    assert hanging.call_count == 2
    assert any(event.get("text") == "救场" for event in events)


@pytest.mark.asyncio
async def test_router_retries_transient_then_succeeds_same_provider():
    flaky = TransientThenOKProvider()
    router = LLMRouter(
        providers={"flaky": flaky},
        fallback_chain=["flaky"],
        timeout_seconds=1.0,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    events: list[dict] = []
    async for event in router.stream_with_tools([], [], provider_name="flaky"):
        events.append(event)

    assert flaky.call_count == 2
    assert any(event.get("text") == "重试成功" for event in events)


class NonTransientFailingProvider(LLMProvider):
    """Raises an auth-style 4xx error: must NOT be retried."""

    def __init__(self) -> None:
        self.call_count = 0

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048, response_format=None):
        self.call_count += 1
        raise AuthError("invalid api key")
        if False:
            yield {}


@pytest.mark.asyncio
async def test_router_does_not_retry_non_transient_within_provider():
    failing = NonTransientFailingProvider()
    backup = FakeProvider("救场")
    router = LLMRouter(
        providers={"bad": failing, "backup": backup},
        fallback_chain=["bad", "backup"],
        timeout_seconds=1.0,
        max_retries=2,
        retry_backoff_seconds=0.0,
    )

    events: list[dict] = []
    async for event in router.stream_with_tools([], [], provider_name="bad"):
        events.append(event)

    # 4xx should be a fail-fast: exactly 1 call into the failing provider.
    assert failing.call_count == 1
    # Then the chain falls through to the backup.
    assert any(event.get("text") == "救场" for event in events)


class MidStreamStallProvider(LLMProvider):
    """First chunk arrives instantly, then the stream stalls forever.

    Mirrors the production failure mode where an upstream LLM streams a few
    tokens and then silently stops emitting chunks without closing the
    underlying connection (no EOF, no error). Without per-chunk timeout
    handling the router will hang indefinitely on the second iteration.
    """

    def __init__(self) -> None:
        self.call_count = 0

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048, response_format=None):
        self.call_count += 1
        yield {"type": "text_delta", "text": "first"}
        await asyncio.sleep(10)
        yield {"type": "text_delta", "text": "never reached"}


@pytest.mark.asyncio
async def test_router_mid_stream_stall_raises_timeout_after_first_event():
    stalling = MidStreamStallProvider()
    router = LLMRouter(
        providers={"stall": stalling},
        fallback_chain=["stall"],
        timeout_seconds=0.05,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    events: list[dict] = []

    async def consume() -> None:
        async for event in router.stream_with_tools([], [], provider_name="stall"):
            events.append(event)

    start = time.monotonic()
    # Outer cap so a regression doesn't hang CI. The router's per-chunk
    # timeout (0.05s) must fire well before this 2s safety net.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(consume(), timeout=2.0)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"router should fail-fast on mid-stream stall, took {elapsed:.2f}s"
    assert events == [{"type": "text_delta", "text": "first"}]
    # Partial output already streamed → router must not retry within provider.
    assert stalling.call_count == 1


@pytest.mark.asyncio
async def test_router_mid_stream_stall_does_not_fall_back_to_next_provider():
    """Once any event has been yielded to the consumer, a downstream stall
    must propagate to the caller — switching to a fallback provider would
    splice partial output from the stalled stream with a fresh full
    response from the backup, producing garbled content for the consumer.
    """
    stalling = MidStreamStallProvider()
    backup = FakeProvider("救场")
    router = LLMRouter(
        providers={"stall": stalling, "backup": backup},
        fallback_chain=["stall", "backup"],
        timeout_seconds=0.05,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    events: list[dict] = []

    async def consume() -> None:
        async for event in router.stream_with_tools([], [], provider_name="stall"):
            events.append(event)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(consume(), timeout=2.0)

    assert events == [{"type": "text_delta", "text": "first"}]
    # Backup must NOT be called: partial output already flowed from `stall`.
    assert stalling.call_count == 1


def test_is_transient_classification():
    assert _is_transient(asyncio.TimeoutError())
    assert _is_transient(APITimeoutError("x"))

    class FiveHundred(Exception):
        status_code = 503

    assert _is_transient(FiveHundred())
    assert not _is_transient(AuthError("x"))
    assert not _is_transient(ValueError("x"))
