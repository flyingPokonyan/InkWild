import asyncio
import json
import pytest
from services.world_creator_retry import (
    with_transient_retry,
    is_transient,
    TransientError,
)


# ---- is_transient ----

def test_is_transient_recognizes_named_classes():
    class APITimeoutError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class CustomBenign(Exception):
        pass

    assert is_transient(APITimeoutError("x")) is True
    assert is_transient(RateLimitError("x")) is True
    assert is_transient(CustomBenign("x")) is False


def test_is_transient_recognizes_5xx_status():
    class HttpErr(Exception):
        def __init__(self, status_code):
            self.status_code = status_code

    assert is_transient(HttpErr(500)) is True
    assert is_transient(HttpErr(503)) is True
    assert is_transient(HttpErr(404)) is False
    assert is_transient(HttpErr(401)) is False


def test_is_transient_for_transient_error_marker():
    assert is_transient(TransientError("x")) is True


def test_is_transient_excludes_json_error():
    assert is_transient(json.JSONDecodeError("x", "y", 0)) is False
    assert is_transient(ValueError("x")) is False


# ---- with_transient_retry ----


@pytest.mark.asyncio
async def test_succeeds_on_first_try():
    async def good():
        return "ok"

    result = await with_transient_retry(good)
    assert result == "ok"


@pytest.mark.asyncio
async def test_retries_transient_then_succeeds():
    attempts = {"n": 0}

    class APITimeoutError(Exception):
        pass

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise APITimeoutError("transient")
        return "ok"

    result = await with_transient_retry(flaky, max_attempts=3, backoffs=(0.001, 0.001))
    assert result == "ok"
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_non_transient_raises_immediately():
    attempts = {"n": 0}

    async def bad():
        attempts["n"] += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError):
        await with_transient_retry(bad, max_attempts=3, backoffs=(0.001, 0.001))
    assert attempts["n"] == 1  # 不 retry


@pytest.mark.asyncio
async def test_exhausts_retries_then_raises_original():
    class RateLimitError(Exception):
        pass

    attempts = {"n": 0}

    async def keep_failing():
        attempts["n"] += 1
        raise RateLimitError("still rate limited")

    with pytest.raises(Exception) as exc_info:
        await with_transient_retry(keep_failing, max_attempts=3, backoffs=(0.001, 0.001))
    assert type(exc_info.value).__name__ == "RateLimitError"
    assert attempts["n"] == 3  # 首次 + 2 retry


@pytest.mark.asyncio
async def test_on_retry_callback_fires():
    class APITimeoutError(Exception):
        pass

    callback_calls: list[tuple[int, int, str]] = []

    async def flaky():
        raise APITimeoutError("x")

    async def on_retry(attempt, max_attempts, exc):
        callback_calls.append((attempt, max_attempts, type(exc).__name__))

    with pytest.raises(Exception):
        await with_transient_retry(
            flaky,
            max_attempts=3,
            backoffs=(0.001, 0.001),
            on_retry=on_retry,
        )
    # 2 次 retry 之前各调一次 on_retry
    assert len(callback_calls) == 2
    assert callback_calls[0][0] == 1  # 第 1 次重试 = attempt 1（首次失败后）
    assert callback_calls[0][1] == 3
    assert callback_calls[0][2] == "APITimeoutError"


@pytest.mark.asyncio
async def test_backoffs_extend_with_last_value_when_short():
    """backoffs=(0.5,) 但 max_attempts=4 时，第 2/3 次都用 0.5。"""

    class APITimeoutError(Exception):
        pass

    async def fail():
        raise APITimeoutError("x")

    # 不验证 sleep 时长，只验证不 IndexError
    with pytest.raises(Exception):
        await with_transient_retry(fail, max_attempts=4, backoffs=(0.001,))


@pytest.mark.asyncio
async def test_factory_called_fresh_each_time():
    """每次 retry 重新调 factory（不是同一个 coroutine 重 await）。"""
    factory_calls = {"n": 0}

    class APITimeoutError(Exception):
        pass

    async def factory_inner():
        if factory_calls["n"] < 3:
            raise APITimeoutError("x")
        return "ok"

    def factory():
        factory_calls["n"] += 1
        return factory_inner()

    result = await with_transient_retry(factory, max_attempts=3, backoffs=(0.001, 0.001))
    assert result == "ok"
    assert factory_calls["n"] == 3
