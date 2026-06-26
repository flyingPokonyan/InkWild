"""Unit tests for the per-provider API key pool."""
from __future__ import annotations

import pytest

import llm.key_pool as kp
from llm.key_pool import KeyCooldownProvider, KeySwitchingProvider, _is_rate_limit


def setup_function() -> None:
    kp.reset_state()


def test_fingerprint_stable_and_short() -> None:
    fp = kp.fingerprint("sk-abc123")
    assert fp == kp.fingerprint("sk-abc123")
    assert len(fp) == 16
    assert fp != kp.fingerprint("sk-different")


def test_sticky_affinity_maps_same_session_to_same_key() -> None:
    keys = ["k1", "k2", "k3"]
    a = kp.select_key("prov", keys, affinity="session-A")
    b = kp.select_key("prov", keys, affinity="session-A")
    assert a == b
    assert a[0] in keys


def test_round_robin_when_no_affinity() -> None:
    keys = ["k1", "k2", "k3"]
    picks = [kp.select_key("prov", keys, affinity=None)[0] for _ in range(3)]
    assert set(picks) == set(keys)  # cycles through all three


def test_cooldown_key_is_skipped() -> None:
    keys = ["k1", "k2"]
    fp1 = kp.fingerprint("k1")
    kp.report_rate_limited("prov", fp1, cooldown_s=100.0, now=0.0)
    # affinity that would otherwise land on k1 must now avoid it
    for aff in ("a", "b", "c", "d"):
        key, _ = kp.select_key("prov", keys, affinity=aff, now=1.0)
        assert key == "k2"


def test_all_cooled_picks_soonest_to_recover() -> None:
    keys = ["k1", "k2"]
    kp.report_rate_limited("prov", kp.fingerprint("k1"), cooldown_s=10.0, now=0.0)
    kp.report_rate_limited("prov", kp.fingerprint("k2"), cooldown_s=100.0, now=0.0)
    key, _ = kp.select_key("prov", keys, affinity="x", now=1.0)
    assert key == "k1"  # k1 recovers at t=10, k2 at t=100


def test_cooldown_expires() -> None:
    keys = ["k1", "k2"]
    kp.report_rate_limited("prov", kp.fingerprint("k1"), cooldown_s=5.0, now=0.0)
    # after expiry k1 is available again
    available = {kp.select_key("prov", keys, affinity=a, now=10.0)[0] for a in "abcd"}
    assert "k1" in available


# ─────────────── KeyCooldownProvider wrapper ───────────────


class _FakeRateLimit(Exception):
    """Stands in for openai.RateLimitError (matched by class name)."""


_FakeRateLimit.__name__ = "RateLimitError"


class _BoomProvider:
    model = "fake"

    def __init__(self, exc: Exception):
        self._exc = exc

    async def stream_with_tools(self, *a, **k):
        if False:
            yield {}
        raise self._exc

    async def stream_json(self, *a, **k):
        if False:
            yield {}
        raise self._exc


def test_is_rate_limit_by_class_name() -> None:
    assert _is_rate_limit(_FakeRateLimit("429"))


def test_is_rate_limit_by_status_code() -> None:
    exc = Exception("x")
    exc.status_code = 429
    assert _is_rate_limit(exc)
    exc2 = Exception("y")
    exc2.status_code = 500
    assert not _is_rate_limit(exc2)


async def test_wrapper_reports_cooldown_on_rate_limit_and_reraises() -> None:
    kp.reset_state()
    fp = kp.fingerprint("k1")
    wrapped = KeyCooldownProvider(_BoomProvider(_FakeRateLimit("429")), provider_id="p", fp=fp)
    with pytest.raises(Exception):
        async for _ in wrapped.stream_with_tools([], []):
            pass
    # k1 is now cooling -> a 2-key pool skips it
    key, _ = kp.select_key("p", ["k1", "k2"], affinity="any")
    assert key == "k2"


async def test_wrapper_does_not_cooldown_on_other_errors() -> None:
    kp.reset_state()
    fp = kp.fingerprint("k1")
    wrapped = KeyCooldownProvider(_BoomProvider(ValueError("nope")), provider_id="p", fp=fp)
    with pytest.raises(ValueError):
        async for _ in wrapped.stream_with_tools([], []):
            pass
    assert kp._cooldowns == {}  # no cooldown recorded


def _affinity_for_key(provider_id: str, keys: list[str], target: str) -> str:
    for idx in range(1000):
        affinity = f"affinity-{idx}"
        if kp.select_key(provider_id, keys, affinity=affinity)[0] == target:
            kp.reset_state()
            return affinity
    raise AssertionError(f"could not find affinity for {target}")


class _KeyedProvider:
    model = "fake"

    def __init__(self, key: str, calls: list[str]):
        self._key = key
        self._calls = calls

    async def stream_with_tools(self, *a, **k):
        self._calls.append(self._key)
        if self._key == "k1":
            raise _FakeRateLimit("429")
        yield {"type": "text_delta", "text": "ok"}

    async def stream_json(self, *a, **k):
        self._calls.append(self._key)
        if self._key == "k1":
            raise _FakeRateLimit("429")
        yield {"type": "text_delta", "text": "ok"}


async def test_key_switching_provider_tries_next_key_before_yield() -> None:
    keys = ["k1", "k2"]
    affinity = _affinity_for_key("p", keys, "k1")
    calls: list[str] = []
    wrapped = KeySwitchingProvider(
        provider_id="p",
        keys=keys,
        affinity=affinity,
        build=lambda key: _KeyedProvider(key, calls),
        model="fake",
    )

    events = [event async for event in wrapped.stream_with_tools([], [])]

    assert events == [{"type": "text_delta", "text": "ok"}]
    assert calls == ["k1", "k2"]


async def test_key_switching_provider_single_key_reraises() -> None:
    calls: list[str] = []
    wrapped = KeySwitchingProvider(
        provider_id="p",
        keys=["k1"],
        affinity="same",
        build=lambda key: _KeyedProvider(key, calls),
        model="fake",
    )

    with pytest.raises(_FakeRateLimit):
        async for _ in wrapped.stream_with_tools([], []):
            pass

    assert calls == ["k1"]


class _WebSearchProvider:
    model = "fake"

    def __init__(self, key: str):
        self._key = key

    async def web_search(self, *a, **k):
        return {"key": self._key, "args": a}


class _NoWebSearchProvider:
    model = "fake"

    def __init__(self, key: str):
        self._key = key


async def test_key_switching_provider_proxies_web_search() -> None:
    """识别联网兜底依赖 wrapper 透传 web_search 到 grok inner（slot 化后的回归防线）。"""
    wrapped = KeySwitchingProvider(
        provider_id="pws",
        keys=["k1"],
        affinity="same",
        build=lambda key: _WebSearchProvider(key),
        model="fake",
    )

    out = await wrapped.web_search("十日终焉")

    assert out == {"key": "k1", "args": ("十日终焉",)}


async def test_key_switching_provider_web_search_raises_when_inner_lacks_it() -> None:
    """inner 非 grok（无 web_search）→ AttributeError，让 getattr 守卫的调用方干净退化。"""
    wrapped = KeySwitchingProvider(
        provider_id="pnows",
        keys=["k1"],
        affinity="same",
        build=lambda key: _NoWebSearchProvider(key),
        model="fake",
    )

    with pytest.raises(AttributeError):
        await wrapped.web_search("x")
