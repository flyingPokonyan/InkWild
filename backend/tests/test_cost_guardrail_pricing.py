"""Tests for estimate_usage_cost_cents with pricing dict support (Task A2)."""
from engine.cost_guardrail import estimate_usage_cost_cents


def test_uses_provider_pricing_when_present():
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000}
    pricing = {
        "input_price_cents_per_million_tokens": 200,
        "output_price_cents_per_million_tokens": 800,
    }
    cost = estimate_usage_cost_cents(usage, pricing=pricing)
    # 1M * 200 / 1M + 0.5M * 800 / 1M = 200 + 400 = 600
    assert cost == 600


def test_falls_back_to_env_when_pricing_null():
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    pricing = {
        "input_price_cents_per_million_tokens": None,
        "output_price_cents_per_million_tokens": None,
    }
    cost = estimate_usage_cost_cents(usage, pricing=pricing, env_input_cents=300)
    assert cost == 300


def test_returns_zero_when_no_pricing_no_env():
    usage = {"input_tokens": 1_000_000}
    cost = estimate_usage_cost_cents(usage)
    assert cost == 0


def test_cost_cents_field_overrides_estimate():
    usage = {"input_tokens": 1_000_000, "cost_cents": 999}
    pricing = {"input_price_cents_per_million_tokens": 200}
    cost = estimate_usage_cost_cents(usage, pricing=pricing)
    assert cost == 999
