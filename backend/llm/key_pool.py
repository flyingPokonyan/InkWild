"""Per-provider API key pool: sticky selection + rate-limit cooldown.

Providers may carry multiple API keys to spread load across an upstream's
per-key concurrency / RPM limits. This module decides *which* key a given
provider build uses, and remembers which keys are currently rate-limited so
they can be skipped.

Selection is **sticky by affinity** (a game ``session_id`` or generation
``task_id``): the same session deterministically maps to the same key,
preserving the upstream prompt cache for that session, while different
sessions fan out across keys. With no affinity, a per-provider round-robin
counter is used instead.

State (round-robin counters + cooldown deadlines) is process-local. Under
multiple workers each process keeps its own view — a soft optimisation, not
a correctness guarantee. Cross-process coordination (Redis) is a future step.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from typing import AsyncIterator

import structlog

from llm.base import ImageGenerator, ImageResult, LLMProvider

logger = structlog.get_logger()

# (provider_id, fingerprint) -> monotonic deadline after which the key is usable again.
_cooldowns: dict[tuple[str, str], float] = {}
# provider_id -> next round-robin index (used when no affinity is available).
_rr_counters: dict[str, int] = {}
_lock = threading.Lock()


def fingerprint(key: str) -> str:
    """Stable short id for a key. Cooldowns / logs reference this, never the raw key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _stable_hash(value: str) -> int:
    """PYTHONHASHSEED-independent hash (builtin ``hash()`` is salted per process)."""
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")


def _cooldown_seconds() -> float:
    from config import settings

    return float(getattr(settings, "key_cooldown_seconds", 45.0))


def select_key(
    provider_id: str,
    keys: list[str],
    affinity: str | None,
    *,
    now: float | None = None,
) -> tuple[str, str]:
    """Pick one key for this provider build. Returns ``(key, fingerprint)``.

    - Keys in cooldown are skipped.
    - If every key is cooling down, the one whose cooldown expires soonest is
      used anyway (never hard-fail just because all keys were recently limited).
    - Among available keys: sticky by ``affinity`` when set, else round-robin.
    """
    if not keys:
        raise ValueError("select_key requires at least one key")
    now = time.monotonic() if now is None else now

    fps = [(k, fingerprint(k)) for k in keys]
    with _lock:
        available = [
            (k, fp)
            for (k, fp) in fps
            if _cooldowns.get((provider_id, fp), 0.0) <= now
        ]
        if not available:
            return min(fps, key=lambda kf: _cooldowns.get((provider_id, kf[1]), 0.0))
        if affinity:
            return available[_stable_hash(affinity) % len(available)]
        n = _rr_counters.get(provider_id, 0)
        _rr_counters[provider_id] = n + 1
        return available[n % len(available)]


def report_rate_limited(
    provider_id: str,
    fp: str,
    *,
    cooldown_s: float | None = None,
    now: float | None = None,
) -> None:
    """Mark a key as rate-limited; it'll be skipped until the cooldown expires."""
    now = time.monotonic() if now is None else now
    cd = _cooldown_seconds() if cooldown_s is None else cooldown_s
    with _lock:
        _cooldowns[(provider_id, fp)] = now + cd
    logger.info("llm.key_cooldown", provider_id=provider_id, fp=fp, cooldown_s=cd)


def reset_state() -> None:
    """Test helper: clear all cooldowns + round-robin counters."""
    with _lock:
        _cooldowns.clear()
        _rr_counters.clear()


def _is_rate_limit(exc: BaseException) -> bool:
    """Whether an exception is an upstream rate-limit (HTTP 429)."""
    if exc.__class__.__name__ == "RateLimitError":
        return True
    status = _status_code(exc)
    return status == 429


def _status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


_KEY_SWITCH_EXC_NAMES = frozenset(
    {
        "APIConnectionError",
        "APITimeoutError",
        "AuthenticationError",
        "ConnectError",
        "ConnectTimeout",
        "InternalServerError",
        "PermissionDeniedError",
        "RateLimitError",
        "ReadTimeout",
        "RemoteProtocolError",
        "ServerDisconnectedError",
    }
)


def _is_key_switchable(exc: BaseException) -> bool:
    """Whether another key might succeed for the same request.

    This intentionally covers quota/auth/rate-limit/status failures but avoids
    retrying arbitrary bad-request errors (for example malformed tool schemas).
    """
    if exc.__class__.__name__ in _KEY_SWITCH_EXC_NAMES:
        return True
    status = _status_code(exc)
    if status in {401, 402, 403, 408, 409, 429}:
        return True
    return bool(status and status >= 500)


def _unique_key_count(keys: list[str]) -> int:
    return len({fingerprint(k) for k in keys})


class KeySwitchingProvider(LLMProvider):
    """Build a fresh inner provider per attempt and switch keys on key-ish failures.

    Selection remains sticky by affinity while the chosen key is healthy. If the
    selected key fails before any event is yielded, it is cooled down and the
    next available key is tried. Once content has streamed, exceptions are
    propagated to avoid splicing together partial outputs from different keys.
    """

    def __init__(
        self,
        *,
        provider_id: str,
        keys: list[str],
        affinity: str | None,
        build: Callable[[str], LLMProvider],
        model: str | None = None,
    ):
        if not keys:
            raise ValueError("KeySwitchingProvider requires at least one key")
        self._provider_id = provider_id
        self._keys = keys
        self._affinity = affinity
        self._build = build
        self._model = model

    @property
    def model(self):  # noqa: ANN201
        return self._model

    async def stream_with_tools(self, *args, **kwargs) -> AsyncIterator[dict]:
        attempted: set[str] = set()
        key_count = _unique_key_count(self._keys)
        last_exc: BaseException | None = None

        while len(attempted) < key_count:
            key, fp = select_key(self._provider_id, self._keys, self._affinity)
            if fp in attempted:
                break
            attempted.add(fp)
            inner = self._build(key)
            yielded_any = False
            try:
                async for ev in inner.stream_with_tools(*args, **kwargs):
                    yielded_any = True
                    yield ev
                return
            except Exception as exc:  # noqa: BLE001 - key switch decision below
                if yielded_any or key_count <= 1 or not _is_key_switchable(exc):
                    raise
                last_exc = exc
                report_rate_limited(self._provider_id, fp)
                logger.warning(
                    "llm.key_switch",
                    provider_id=self._provider_id,
                    fp=fp,
                    error_type=exc.__class__.__name__,
                    status_code=_status_code(exc),
                    attempted=len(attempted),
                    key_count=key_count,
                )
                continue

        if last_exc is not None:
            raise last_exc

    async def stream_json(self, *args, **kwargs) -> AsyncIterator[dict]:
        attempted: set[str] = set()
        key_count = _unique_key_count(self._keys)
        last_exc: BaseException | None = None

        while len(attempted) < key_count:
            key, fp = select_key(self._provider_id, self._keys, self._affinity)
            if fp in attempted:
                break
            attempted.add(fp)
            inner = self._build(key)
            yielded_any = False
            try:
                async for ev in inner.stream_json(*args, **kwargs):
                    yielded_any = True
                    yield ev
                return
            except Exception as exc:  # noqa: BLE001 - key switch decision below
                if yielded_any or key_count <= 1 or not _is_key_switchable(exc):
                    raise
                last_exc = exc
                report_rate_limited(self._provider_id, fp)
                logger.warning(
                    "llm.key_switch",
                    provider_id=self._provider_id,
                    fp=fp,
                    error_type=exc.__class__.__name__,
                    status_code=_status_code(exc),
                    attempted=len(attempted),
                    key_count=key_count,
                )
                continue

        if last_exc is not None:
            raise last_exc

    async def web_search(self, *args, **kwargs):
        """Proxy Grok Live Search to the inner provider, switching keys on
        key-ish failures (mirrors ``stream_with_tools`` rotation, single awaited
        result). Raises ``AttributeError`` when the bound model's provider has no
        ``web_search`` (non-grok), so ``getattr``-guarded callers (IP 识别联网兜底)
        degrade to parametric-only cleanly instead of silently losing the wrapper's
        web_search capability."""
        attempted: set[str] = set()
        key_count = _unique_key_count(self._keys)
        last_exc: BaseException | None = None

        while len(attempted) < key_count:
            key, fp = select_key(self._provider_id, self._keys, self._affinity)
            if fp in attempted:
                break
            attempted.add(fp)
            inner = self._build(key)
            inner_ws = getattr(inner, "web_search", None)
            if inner_ws is None:
                raise AttributeError("inner provider has no web_search")
            try:
                return await inner_ws(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - key switch decision below
                if key_count <= 1 or not _is_key_switchable(exc):
                    raise
                last_exc = exc
                report_rate_limited(self._provider_id, fp)
                logger.warning(
                    "llm.key_switch",
                    provider_id=self._provider_id,
                    fp=fp,
                    error_type=exc.__class__.__name__,
                    status_code=_status_code(exc),
                    attempted=len(attempted),
                    key_count=key_count,
                )
                continue

        if last_exc is not None:
            raise last_exc
        raise AttributeError("inner provider has no web_search")


class KeyCooldownProvider(LLMProvider):
    """Transparent passthrough that puts its key in cooldown on a 429.

    Re-raises every exception so ``LLMRouter``'s existing retry / fallback
    still runs. Exposes ``.model`` because the router reads it for identity
    stamping.
    """

    def __init__(self, inner: LLMProvider, *, provider_id: str, fp: str):
        self._inner = inner
        self._provider_id = provider_id
        self._fp = fp

    @property
    def model(self):  # noqa: ANN201 - mirrors inner provider's attribute
        return getattr(self._inner, "model", None)

    async def stream_with_tools(self, *args, **kwargs) -> AsyncIterator[dict]:
        try:
            async for ev in self._inner.stream_with_tools(*args, **kwargs):
                yield ev
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            if _is_rate_limit(exc):
                report_rate_limited(self._provider_id, self._fp)
            raise

    async def stream_json(self, *args, **kwargs) -> AsyncIterator[dict]:
        try:
            async for ev in self._inner.stream_json(*args, **kwargs):
                yield ev
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            if _is_rate_limit(exc):
                report_rate_limited(self._provider_id, self._fp)
            raise

    async def web_search(self, *args, **kwargs):
        """Passthrough Grok Live Search with cooldown-on-429 (mirrors the stream
        methods). AttributeError if inner has no web_search (non-grok)."""
        try:
            return await self._inner.web_search(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            if _is_rate_limit(exc):
                report_rate_limited(self._provider_id, self._fp)
            raise


class KeyCooldownImageGenerator(ImageGenerator):
    """Same cooldown-on-429 behaviour for the image generation path."""

    def __init__(self, inner: ImageGenerator, *, provider_id: str, fp: str):
        self._inner = inner
        self._provider_id = provider_id
        self._fp = fp

    @property
    def model(self):  # noqa: ANN201
        return getattr(self._inner, "model", None)

    async def generate_image(self, *args, **kwargs) -> ImageResult:
        try:
            return await self._inner.generate_image(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            if _is_rate_limit(exc):
                report_rate_limited(self._provider_id, self._fp)
            raise
