from engine.cost_guardrail import (
    CostGuardrailStatus,
    classify_session_cost,
    estimate_usage_cost_cents,
)


def test_classify_session_cost_uses_soft_warn_and_hard_cap_thresholds():
    assert classify_session_cost(499, soft_warn_cost_cents=500, hard_cap_cost_cents=600).status == CostGuardrailStatus.OK
    assert classify_session_cost(500, soft_warn_cost_cents=500, hard_cap_cost_cents=600).status == CostGuardrailStatus.WARN
    assert classify_session_cost(600, soft_warn_cost_cents=500, hard_cap_cost_cents=600).status == CostGuardrailStatus.CAPPED


def test_estimate_usage_cost_prefers_provider_supplied_cost():
    usage = {"input_tokens": 10_000, "output_tokens": 20_000, "cost_cents": 123}

    assert estimate_usage_cost_cents(
        usage,
        input_cost_cents_per_million_tokens=1,
        output_cost_cents_per_million_tokens=1,
    ) == 123


def test_estimate_usage_cost_rounds_up_configured_token_rates():
    usage = {"input_tokens": 1, "output_tokens": 1}

    assert estimate_usage_cost_cents(
        usage,
        input_cost_cents_per_million_tokens=1,
        output_cost_cents_per_million_tokens=1,
    ) == 1
