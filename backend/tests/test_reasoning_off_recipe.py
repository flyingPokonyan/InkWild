"""Unit tests for the host-derived reasoning-off recipe.

Regression guard: a stale/wrong recipe on a known vendor host must NOT be able
to silently leave thinking ON (the bug that caused a ~2x realtime TTFT spike
when DashScope's {"enable_thinking": false} was left on the DeepSeek endpoint).
"""
from types import SimpleNamespace

from services.model_management import _resolve_reasoning_off


def _p(base_url, extra_config=None):
    return SimpleNamespace(base_url=base_url, extra_config=extra_config or {})


def test_deepseek_host_uses_thinking_disabled():
    assert _resolve_reasoning_off(_p("https://api.deepseek.com")) == {"thinking": {"type": "disabled"}}


def test_opencode_host_uses_thinking_disabled():
    # OpenCode proxies DeepSeek and honors the same recipe.
    assert _resolve_reasoning_off(_p("https://opencode.ai/zen/go/v1")) == {"thinking": {"type": "disabled"}}


def test_dashscope_host_uses_enable_thinking():
    assert _resolve_reasoning_off(_p("https://dashscope.aliyuncs.com/compatible-mode/v1")) == {"enable_thinking": False}


def test_known_host_overrides_wrong_extra_config():
    # The exact regression: DashScope recipe wrongly left on the DeepSeek endpoint.
    # Host derivation must win so thinking is actually disabled.
    p = _p("https://api.deepseek.com", {"reasoning_off": {"enable_thinking": False}})
    assert _resolve_reasoning_off(p) == {"thinking": {"type": "disabled"}}


def test_unknown_host_falls_back_to_explicit_override():
    p = _p("https://my-custom-gateway.example.com/v1", {"reasoning_off": {"foo": "bar"}})
    assert _resolve_reasoning_off(p) == {"foo": "bar"}


def test_unknown_host_no_override_returns_none():
    assert _resolve_reasoning_off(_p("https://mystery.example.com/v1")) is None


def test_empty_base_url_returns_none():
    assert _resolve_reasoning_off(_p("")) is None
