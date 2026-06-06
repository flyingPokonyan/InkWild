"""Pure cost→credit conversion. No DB/IO — fed pricing dicts + raw usage.

Credits are cost-pegged: charged = real_cost(fen) * billing_multiplier. We
compute cost at fractional-fen precision (NOT the integer ``cost_cents``) so
cheap sub-fen calls aren't rounded to zero credits.
"""
from __future__ import annotations

from models.credit import CREDIT_UNIT_SCALE


def usage_to_cost_fen(
    *,
    input_tokens: int,
    output_tokens: int,
    image_count: int,
    pricing: dict | None,
    cache_hit_tokens: int = 0,
    cache_miss_tokens: int = 0,
) -> float:
    """Fractional cost in fen (CNY 分). Sub-fen precision preserved.

    Phase 2 cache-aware: prompt-cache-hit input tokens bill at
    ``cached_input_price_cents_per_million_tokens`` when configured; a ``None``
    cached price falls back to the full input price (Phase 1 behavior). When the
    provider reports no cache breakdown (both counts 0), all input is billed at
    the full price as before.
    """
    if not pricing:
        return 0.0
    input_price = pricing.get("input_price_cents_per_million_tokens") or 0
    output_price = pricing.get("output_price_cents_per_million_tokens") or 0
    image_price = pricing.get("image_price_cents_per_image") or 0
    cached_raw = pricing.get("cached_input_price_cents_per_million_tokens")
    cached_price = cached_raw if cached_raw is not None else input_price

    hit = int(cache_hit_tokens or 0)
    miss = int(cache_miss_tokens or 0)
    if hit == 0 and miss == 0:
        # No cache breakdown reported — bill all input at full price.
        miss = int(input_tokens or 0)
    token_fen = (miss * input_price + hit * cached_price + output_tokens * output_price) / 1_000_000
    return token_fen + image_count * image_price


def cost_fen_to_units(cost_fen: float, *, billing_multiplier_milli: int) -> int:
    """Fractional fen → integer credit units, applying the billing multiplier.

    ``billing_multiplier_milli`` is x1000 (1000 == 1.0x break-even).
    """
    if cost_fen <= 0:
        return 0
    return round(cost_fen * (billing_multiplier_milli / 1000) * CREDIT_UNIT_SCALE)


def units_to_credits(units: int) -> float:
    """Display helper: internal units → credits (4 dp)."""
    return round(units / CREDIT_UNIT_SCALE, 4)


def credits_to_units(credits: float) -> int:
    return round(credits * CREDIT_UNIT_SCALE)
