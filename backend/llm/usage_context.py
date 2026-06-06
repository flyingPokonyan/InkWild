"""Ambient ``UsageContext`` for AOP-style LLM cost attribution.

Every LLM call (text via ``LLMRouter`` or image via ``MeteredImageGenerator``)
has its cost attributed to whichever ``UsageContext`` is active in the
current ``contextvars.Context``. Entrypoints (``game_service``,
``generation_task_service``, etc.) set the context once; nested awaits
and ``asyncio.create_task`` / ``asyncio.gather`` inherit it automatically.

Nesting merges with the parent: passing only ``phase`` keeps the parent's
``purpose`` / ``session_id`` / ``task_id`` / ``user_id`` intact so callers
can tag a sub-stage without re-stating the identity.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Iterator


# Valid ``purpose`` values. Sink writes that lie outside this set are
# rejected at recording time (logged + dropped) so a typo at a single
# call site can't silently pollute analytics buckets.
VALID_PURPOSES: frozenset[str] = frozenset(
    {
        "game",
        "moderation",
        "reflection",
        "compression",
        "world_gen",
        "script_gen",
        "image_gen",
    }
)


@dataclass(frozen=True, slots=True)
class UsageContext:
    """Ambient identity attached to a single LLM/image call.

    ``purpose`` is mandatory at sink time; the other fields are optional
    but at least one of ``session_id`` / ``task_id`` must be set to
    satisfy the ``token_usage`` CHECK constraint.
    """

    purpose: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    phase: str | None = None


_usage_context: contextvars.ContextVar[UsageContext | None] = contextvars.ContextVar(
    "usage_context", default=None
)


def current_usage_context() -> UsageContext | None:
    """Return the active ``UsageContext`` or ``None`` if unset."""
    return _usage_context.get()


@contextmanager
def usage_context(
    *,
    purpose: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
    phase: str | None = None,
) -> Iterator[UsageContext]:
    """Push a ``UsageContext`` for the duration of the ``with`` block.

    Any field left as ``None`` inherits from the parent context (so a
    nested block can override just ``phase`` while keeping the rest).
    Safe to use inside ``async def`` — contextvars propagate across
    ``await`` and ``asyncio.create_task`` boundaries.
    """
    parent = _usage_context.get()
    if parent is None:
        new_ctx = UsageContext(
            purpose=purpose,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            phase=phase,
        )
    else:
        new_ctx = replace(
            parent,
            purpose=purpose if purpose is not None else parent.purpose,
            session_id=session_id if session_id is not None else parent.session_id,
            task_id=task_id if task_id is not None else parent.task_id,
            user_id=user_id if user_id is not None else parent.user_id,
            # ``phase`` is the only field that resets to None unless explicit:
            # nested blocks usually want to *replace* the parent's phase, not
            # accidentally carry it.
            phase=phase,
        )

    token = _usage_context.set(new_ctx)
    try:
        yield new_ctx
    finally:
        _usage_context.reset(token)


def push_usage_context(
    *,
    purpose: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
    phase: str | None = None,
) -> contextvars.Token:
    """Imperative ``set``: push a context and return the reset token.

    Use this when a ``with`` block would cause excessive re-indenting of
    a long function body. Pair every call with
    ``pop_usage_context(token)`` in a ``finally`` to guarantee reset.
    Merges with the parent the same way ``usage_context()`` does.
    """
    parent = _usage_context.get()
    if parent is None:
        new_ctx = UsageContext(
            purpose=purpose,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            phase=phase,
        )
    else:
        from dataclasses import replace

        new_ctx = replace(
            parent,
            purpose=purpose if purpose is not None else parent.purpose,
            session_id=session_id if session_id is not None else parent.session_id,
            task_id=task_id if task_id is not None else parent.task_id,
            user_id=user_id if user_id is not None else parent.user_id,
            phase=phase,
        )
    return _usage_context.set(new_ctx)


def pop_usage_context(token: contextvars.Token) -> None:
    """Reset the context using the token returned by ``push_usage_context``."""
    _usage_context.reset(token)


# ---------------------------------------------------------------------------
# Per-action usage accumulator (credits settlement)
# ---------------------------------------------------------------------------
# Independent of UsageContext: an action boundary (game turn / generation task)
# opens an accumulator; every text/image call feeds its real usage in
# synchronously at emission time — decoupled from the best-effort DB sink — so
# the boundary can settle credits against *actual* usage. Per-model entries
# because one turn may span several models (e.g. v4-pro + v4-flash).


class UsageAccumulator:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def add(
        self,
        *,
        provider_name: str | None,
        model_id: str | None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        image_count: int = 0,
        cache_hit_tokens: int = 0,
        cache_miss_tokens: int = 0,
    ) -> None:
        self.entries.append(
            {
                "provider_name": provider_name,
                "model_id": model_id,
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
                "image_count": int(image_count or 0),
                "cache_hit_tokens": int(cache_hit_tokens or 0),
                "cache_miss_tokens": int(cache_miss_tokens or 0),
            }
        )


_usage_accumulator: contextvars.ContextVar[UsageAccumulator | None] = contextvars.ContextVar(
    "usage_accumulator", default=None
)


def current_usage_accumulator() -> UsageAccumulator | None:
    """Return the active per-action accumulator, or None if no boundary opened one."""
    return _usage_accumulator.get()


@contextmanager
def usage_accumulator() -> Iterator[UsageAccumulator]:
    """Open a fresh accumulator for the duration of an action boundary."""
    acc = UsageAccumulator()
    token = _usage_accumulator.set(acc)
    try:
        yield acc
    finally:
        _usage_accumulator.reset(token)


__all__ = [
    "VALID_PURPOSES",
    "UsageContext",
    "current_usage_context",
    "usage_context",
    "push_usage_context",
    "pop_usage_context",
    "UsageAccumulator",
    "current_usage_accumulator",
    "usage_accumulator",
]
