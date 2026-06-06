"""Pure cost→credit conversion math (no DB)."""
from services.credit_pricing import (
    cost_fen_to_units,
    credits_to_units,
    units_to_credits,
    usage_to_cost_fen,
)

_PRICING = {
    "input_price_cents_per_million_tokens": 313,
    "output_price_cents_per_million_tokens": 626,
    "image_price_cents_per_image": 20,
}


def test_cost_fen_per_dimension():
    assert usage_to_cost_fen(input_tokens=1_000_000, output_tokens=0, image_count=0, pricing=_PRICING) == 313.0
    assert usage_to_cost_fen(input_tokens=0, output_tokens=1_000_000, image_count=0, pricing=_PRICING) == 626.0
    assert usage_to_cost_fen(input_tokens=0, output_tokens=0, image_count=3, pricing=_PRICING) == 60.0


def test_subfen_precision_preserved():
    # 1000 input tokens @313/M = 0.313 fen — must NOT round to 0.
    cost = usage_to_cost_fen(input_tokens=1000, output_tokens=0, image_count=0, pricing=_PRICING)
    assert 0.31 < cost < 0.32


def test_no_pricing_is_free():
    assert usage_to_cost_fen(input_tokens=9999, output_tokens=9999, image_count=5, pricing=None) == 0.0


def test_multiplier_and_scale():
    # 10 fen @ x1 -> 10 credits -> 100000 units
    assert cost_fen_to_units(10.0, billing_multiplier_milli=1000) == 100_000
    # x2 margin -> double the charged units
    assert cost_fen_to_units(10.0, billing_multiplier_milli=2000) == 200_000
    # x3
    assert cost_fen_to_units(10.0, billing_multiplier_milli=3000) == 300_000
    assert cost_fen_to_units(0.0, billing_multiplier_milli=1000) == 0


def test_credit_unit_roundtrip():
    assert units_to_credits(174070) == 17.407
    assert credits_to_units(500) == 5_000_000
    assert credits_to_units(0.5) == 5_000


_PRICING_CACHED = {**_PRICING, "cached_input_price_cents_per_million_tokens": 31}


def test_cache_hit_billed_at_cached_price():
    # 1M input = 600k cache-hit + 400k miss: 400k@313 + 600k@31.
    cost = usage_to_cost_fen(
        input_tokens=1_000_000,
        output_tokens=0,
        image_count=0,
        pricing=_PRICING_CACHED,
        cache_hit_tokens=600_000,
        cache_miss_tokens=400_000,
    )
    assert cost == (400_000 * 313 + 600_000 * 31) / 1_000_000  # 143.8


def test_cache_hit_only():
    cost = usage_to_cost_fen(
        input_tokens=500_000,
        output_tokens=0,
        image_count=0,
        pricing=_PRICING_CACHED,
        cache_hit_tokens=500_000,
        cache_miss_tokens=0,
    )
    assert cost == 500_000 * 31 / 1_000_000  # 15.5


def test_null_cached_price_falls_back_to_full():
    # No cached price configured -> hits bill at full input price (no change).
    cost = usage_to_cost_fen(
        input_tokens=1_000_000,
        output_tokens=0,
        image_count=0,
        pricing=_PRICING,
        cache_hit_tokens=600_000,
        cache_miss_tokens=400_000,
    )
    assert cost == 313.0


def test_no_cache_breakdown_bills_all_input():
    # Both counts 0 -> all input_tokens billed at full price (Phase 1 behavior).
    cost = usage_to_cost_fen(
        input_tokens=1_000_000, output_tokens=0, image_count=0, pricing=_PRICING_CACHED
    )
    assert cost == 313.0
