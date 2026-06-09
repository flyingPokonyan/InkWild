from dataclasses import dataclass
from enum import StrEnum


class CostGuardrailStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    CAPPED = "capped"


@dataclass(frozen=True)
class CostGuardrailResult:
    status: CostGuardrailStatus
    total_cost_cents: int
    soft_warn_cost_cents: int
    hard_cap_cost_cents: int


def classify_session_cost(
    total_cost_cents: int,
    *,
    soft_warn_cost_cents: int,
    hard_cap_cost_cents: int,
) -> CostGuardrailResult:
    """Classify cumulative session spend.

    Cost values use the existing TokenUsage.cost_cents unit. For this product,
    settings treat one "cent" as one CNY fen: ¥5 == 500, ¥6 == 600.
    """
    # A threshold of <= 0 disables that tier (no warn / no cap), so the
    # guardrail can be turned off entirely via config without magic numbers.
    if hard_cap_cost_cents > 0 and total_cost_cents >= hard_cap_cost_cents:
        status = CostGuardrailStatus.CAPPED
    elif soft_warn_cost_cents > 0 and total_cost_cents >= soft_warn_cost_cents:
        status = CostGuardrailStatus.WARN
    else:
        status = CostGuardrailStatus.OK

    return CostGuardrailResult(
        status=status,
        total_cost_cents=total_cost_cents,
        soft_warn_cost_cents=soft_warn_cost_cents,
        hard_cap_cost_cents=hard_cap_cost_cents,
    )


def estimate_usage_cost_cents(
    usage: dict | None,
    *,
    pricing: dict | None = None,
    input_cost_cents_per_million_tokens: int = 0,
    output_cost_cents_per_million_tokens: int = 0,
    env_input_cents: int = 0,
    env_output_cents: int = 0,
    env_image_cents: int = 0,
) -> int:
    """Estimate cost in cents.

    Priority:
      1. usage["cost_cents"] (provider self-reported)
      2. pricing dict fields (from provider_models table)
      3. env fallback values (env_input_cents / env_output_cents / env_image_cents)
      4. legacy positional-kwargs (input_cost_cents_per_million_tokens /
         output_cost_cents_per_million_tokens) for backward compat
    Returns 0 if nothing applicable.
    """
    if not usage:
        return 0

    if usage.get("cost_cents") is not None:
        return max(int(usage.get("cost_cents") or 0), 0)

    input_tokens = max(int(usage.get("input_tokens") or 0), 0)
    output_tokens = max(int(usage.get("output_tokens") or 0), 0)
    image_count = max(int(usage.get("image_count") or 0), 0)

    # If a pricing dict was supplied (from provider_models), use it with
    # per-dimension ceiling arithmetic.  Fall back to env kwargs first, then
    # legacy positional-style kwargs.
    if pricing is not None:
        input_price = (
            pricing.get("input_price_cents_per_million_tokens")
            or env_input_cents
            or input_cost_cents_per_million_tokens
        )
        output_price = (
            pricing.get("output_price_cents_per_million_tokens")
            or env_output_cents
            or output_cost_cents_per_million_tokens
        )
        image_price = pricing.get("image_price_cents_per_image") or env_image_cents

        # Prefix-cache aware: bill cache-hit input at the cached price (falls
        # back to the full input price when not configured). Without this the
        # column over-counts ~4x once hit rates are high. Mirrors
        # credit_pricing.usage_to_cost_fen (the actual debit path).
        hit = max(int(usage.get("cache_hit_tokens") or 0), 0)
        miss = max(int(usage.get("cache_miss_tokens") or 0), 0)
        if hit == 0 and miss == 0:
            miss = input_tokens  # no breakdown reported → all input full price
        cached_raw = pricing.get("cached_input_price_cents_per_million_tokens")
        cached_price = cached_raw if cached_raw is not None else input_price

        cents = 0
        if input_price or cached_price:
            cents += (miss * input_price + hit * cached_price + 999_999) // 1_000_000
        if output_price and output_tokens:
            cents += (output_tokens * output_price + 999_999) // 1_000_000
        if image_price and image_count:
            cents += image_count * image_price
        return cents

    # Legacy path (no pricing dict): combine raw cost and apply a single
    # ceiling to preserve the original rounding behaviour expected by existing
    # callers and tests.
    effective_input = env_input_cents or input_cost_cents_per_million_tokens
    effective_output = env_output_cents or output_cost_cents_per_million_tokens
    raw_cost = (
        input_tokens * effective_input
        + output_tokens * effective_output
    )
    if raw_cost <= 0:
        return 0
    return (raw_cost + 999_999) // 1_000_000
