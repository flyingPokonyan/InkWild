"""LLM stage transient retry helper（spec §6.1）.

封装"对 transient 异常 retry 1-2 次，对 4xx / json / 其他立即失败"逻辑。
独立模块 — 任何阶段 builder 直接调 with_transient_retry(lambda: do_llm_call()) 包裹即可。
"""
import asyncio
from typing import Any, Awaitable, Callable, TypeVar

import structlog

logger = structlog.get_logger()

T = TypeVar("T")


class TransientError(Exception):
    """显式 transient 标记（caller 可用此包裹其他异常表示要 retry）。"""


TRANSIENT_EXCEPTION_NAMES = frozenset({
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "APIError",
    "ServerError",
    "ConnectionError",
    "TimeoutError",
})


def is_transient(exc: BaseException) -> bool:
    """判断异常是否 transient（按类名 + 5xx 状态码）。"""
    if isinstance(exc, TransientError):
        return True
    if type(exc).__name__ in TRANSIENT_EXCEPTION_NAMES:
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and 500 <= status < 600:
        return True
    return False


async def with_transient_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    backoffs: tuple[float, ...] = (1.0, 3.0),
    on_retry: Callable[[int, int, BaseException], Awaitable[None]] | None = None,
) -> T:
    """对 coro_factory() 调用做 transient retry。

    - 每次重新调用 coro_factory()（不是 await 同一个 coroutine）
    - 4xx / json parse error / 其他非 transient 异常立即抛出
    - 最后一次仍失败则抛出原异常（不包裹）
    - on_retry(attempt, max_attempts, exc) 在每次重试前调用（用于 emit warning 事件）

    backoffs 长度必须 ≥ max_attempts - 1，否则用最后一项重复。
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await coro_factory()
        except BaseException as exc:
            if not is_transient(exc) or attempt + 1 >= max_attempts:
                raise
            last_exc = exc
            if on_retry is not None:
                try:
                    await on_retry(attempt + 1, max_attempts, exc)
                except Exception:  # noqa: BLE001
                    logger.warning("retry_on_retry_callback_failed", exc_info=True)
            sleep_idx = min(attempt, len(backoffs) - 1)
            sleep_for = backoffs[sleep_idx] if backoffs else 0
            await asyncio.sleep(sleep_for)
    # 不应到达；保险
    if last_exc:
        raise last_exc
    raise RuntimeError("with_transient_retry exhausted without exception")
