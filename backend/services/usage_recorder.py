"""LLM token / image usage sink.

Single point of insertion for ``token_usage`` rows. Called from the
``LLMRouter`` text path and the ``MeteredImageGenerator`` image path —
business code never writes to ``token_usage`` directly.

Two contracts:

* **Best-effort.** Any exception inside the recorder is swallowed and
  logged. Recording must never break the LLM call it's measuring.
* **Independent transaction.** Each record opens a fresh
  ``async_session`` and commits on its own; recording lifecycle is fully
  decoupled from the caller's DB session.
"""

from __future__ import annotations

import asyncio

import structlog

from config import settings
from database import async_session
from engine.cost_guardrail import estimate_usage_cost_cents
from llm.usage_context import VALID_PURPOSES, UsageContext
from models.game import TokenUsage
from services.pricing_lookup import get_pricing_for

logger = structlog.get_logger()


def _is_attributable(ctx: UsageContext | None) -> bool:
    """Whether a context is well-formed enough to write a row for.

    Skips silently (with a log) if the context is missing the
    ``purpose`` label or fails the at-least-one-of-session-or-task
    invariant from the DB CHECK constraint.
    """
    if ctx is None:
        return False
    if not ctx.purpose or ctx.purpose not in VALID_PURPOSES:
        logger.warning(
            "usage.invalid_purpose",
            purpose=ctx.purpose,
            valid=sorted(VALID_PURPOSES),
        )
        return False
    if not ctx.session_id and not ctx.task_id:
        logger.warning(
            "usage.no_identity",
            purpose=ctx.purpose,
        )
        return False
    return True


async def record_text_usage(event: dict, ctx: UsageContext) -> None:
    """Persist one text LLM call's token usage.

    ``event`` is the ``{"type": "usage", ...}`` payload yielded by
    ``LLMRouter.stream_with_tools`` (already stamped with
    ``provider_name`` / ``model_id`` by the router).
    """
    try:
        if not _is_attributable(ctx):
            return

        provider_name = event.get("provider_name")
        model_id = event.get("model_id")
        input_tokens = max(int(event.get("input_tokens") or 0), 0)
        output_tokens = max(int(event.get("output_tokens") or 0), 0)

        # Prefix-cache observability (DeepSeek-style). Provider fills these
        # only when the upstream returned them; absent fields → unsupported.
        cache_hit = event.get("cache_hit_tokens")
        cache_miss = event.get("cache_miss_tokens")
        if cache_hit is not None or cache_miss is not None:
            hit = int(cache_hit or 0)
            miss = int(cache_miss or 0)
            total = hit + miss
            logger.info(
                "llm.cache",
                purpose=ctx.purpose,
                phase=ctx.phase,
                session_id=ctx.session_id,
                provider_name=provider_name,
                model_id=model_id,
                input_tokens=input_tokens,
                cache_hit_tokens=hit,
                cache_miss_tokens=miss,
                hit_rate=(round(hit / total, 3) if total else None),
            )

        async with async_session() as db:
            pricing = await get_pricing_for(
                db,
                provider_name=provider_name,
                model_id=model_id,
            )
            cost_cents = estimate_usage_cost_cents(
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
                pricing=pricing,
                env_input_cents=settings.game_input_cost_cents_per_million_tokens,
                env_output_cents=settings.game_output_cost_cents_per_million_tokens,
            )
            db.add(
                TokenUsage(
                    session_id=ctx.session_id,
                    task_id=ctx.task_id,
                    purpose=ctx.purpose,
                    phase=ctx.phase,
                    provider=event.get("provider") or settings.llm_provider,
                    model=event.get("model") or settings.llm_default_model,
                    provider_name=provider_name,
                    model_id=model_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    # Persist prefix-cache split when the provider reported it;
                    # absent → NULL (unsupported), distinct from a reported 0.
                    cache_hit_tokens=int(cache_hit) if cache_hit is not None else None,
                    cache_miss_tokens=int(cache_miss) if cache_miss is not None else None,
                    image_count=0,
                    cost_cents=cost_cents,
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — sink must never raise
        logger.warning(
            "usage.text_record_failed",
            error=str(exc),
            error_type=exc.__class__.__name__,
            purpose=getattr(ctx, "purpose", None),
        )


async def record_image_usage(
    *,
    provider_name: str | None,
    model_id: str | None,
    ctx: UsageContext,
    count: int = 1,
) -> None:
    """Persist one image-generation call's count + cost.

    Image providers don't return token counts; we record ``image_count``
    only. ``cost_cents`` is derived from
    ``provider_models.image_price_cents_per_image`` (admin-configurable)
    so the count + admin pricing fully determines spend.
    """
    try:
        if not _is_attributable(ctx):
            return
        if count <= 0:
            return

        async with async_session() as db:
            pricing = await get_pricing_for(
                db,
                provider_name=provider_name,
                model_id=model_id,
            )
            cost_cents = estimate_usage_cost_cents(
                {"image_count": count},
                pricing=pricing,
            )
            db.add(
                TokenUsage(
                    session_id=ctx.session_id,
                    task_id=ctx.task_id,
                    purpose=ctx.purpose,
                    phase=ctx.phase,
                    provider=provider_name or "image",
                    model=model_id or "unknown",
                    provider_name=provider_name,
                    model_id=model_id,
                    input_tokens=0,
                    output_tokens=0,
                    image_count=count,
                    cost_cents=cost_cents,
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — sink must never raise
        logger.warning(
            "usage.image_record_failed",
            error=str(exc),
            error_type=exc.__class__.__name__,
            purpose=getattr(ctx, "purpose", None),
        )


# Strong refs so ``asyncio.create_task``-spawned recording tasks don't
# get GC'd mid-flight (which produces "Task was destroyed but it is
# pending" warnings and silently swallows the row).
_pending_tasks: set[asyncio.Task] = set()


def fire_and_forget_text_usage(event: dict, ctx: UsageContext) -> None:
    """Schedule ``record_text_usage`` on the running loop without awaiting.

    Used by ``LLMRouter`` so usage recording never blocks the consumer
    stream. The task self-deregisters on completion.
    """
    try:
        task = asyncio.create_task(record_text_usage(event, ctx))
    except RuntimeError:
        # No running loop — happens in some sync test setups; drop silently.
        return
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


def fire_and_forget_image_usage(
    *,
    provider_name: str | None,
    model_id: str | None,
    ctx: UsageContext,
    count: int = 1,
) -> None:
    """Schedule ``record_image_usage`` on the running loop without awaiting."""
    try:
        task = asyncio.create_task(
            record_image_usage(
                provider_name=provider_name,
                model_id=model_id,
                ctx=ctx,
                count=count,
            )
        )
    except RuntimeError:
        return
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


__all__ = [
    "record_text_usage",
    "record_image_usage",
    "fire_and_forget_text_usage",
    "fire_and_forget_image_usage",
]
