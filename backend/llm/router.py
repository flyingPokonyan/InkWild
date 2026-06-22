import asyncio
import hashlib
from typing import AsyncIterator

import structlog

from llm.base import LLMProvider
from llm.usage_context import current_usage_accumulator as _current_usage_accumulator
from llm.usage_context import current_usage_context as _current_usage_context


def _fire_and_forget_text_usage(event: dict, ctx) -> None:
    """Lazy proxy to ``services.usage_recorder.fire_and_forget_text_usage``.

    Imported lazily to avoid a top-level ``llm → services`` import cycle.
    """
    from services.usage_recorder import fire_and_forget_text_usage

    fire_and_forget_text_usage(event, ctx)


def _accumulate_usage(event: dict) -> None:
    """Feed real usage into the active per-action accumulator (credits settle).

    Synchronous + reliable (unlike the best-effort sink): the game-turn /
    generation-task boundary reads this to bill actual usage.
    """
    acc = _current_usage_accumulator()
    if acc is not None:
        acc.add(
            provider_name=event.get("provider_name"),
            model_id=event.get("model_id"),
            input_tokens=event.get("input_tokens") or 0,
            output_tokens=event.get("output_tokens") or 0,
            cache_hit_tokens=event.get("cache_hit_tokens") or 0,
            cache_miss_tokens=event.get("cache_miss_tokens") or 0,
        )


def _log_reasoning_content_observed(
    event: dict,
    *,
    provider: str,
    provider_name: str | None,
    model_id: str | None,
    reasoning_requested: bool | None,
) -> None:
    chunks = int(event.get("reasoning_content_chunks") or 0)
    if not chunks:
        return
    ctx = _current_usage_context()
    logger.warning(
        "llm.reasoning_content_observed",
        provider=provider,
        provider_name=provider_name,
        model_id=model_id,
        chunks=chunks,
        chars=int(event.get("reasoning_content_chars") or 0),
        reasoning_requested=reasoning_requested,
        purpose=ctx.purpose if ctx else None,
        phase=ctx.phase if ctx else None,
    )


logger = structlog.get_logger()

# BUGS #20 — global cap on concurrent in-flight LLM stream calls (across all
# routers and providers). Lazy init so the Semaphore binds to the running
# event loop, not module-load time. Both stream_with_tools and stream_json
# acquire this; the semaphore is released when the stream generator exits.
_global_concurrency_sem: asyncio.Semaphore | None = None


async def _acquire_global_concurrency_slot() -> asyncio.Semaphore:
    global _global_concurrency_sem
    if _global_concurrency_sem is None:
        from config import settings
        cap = max(1, int(getattr(settings, "llm_global_concurrency", 8)))
        _global_concurrency_sem = asyncio.Semaphore(cap)
    sem = _global_concurrency_sem
    await sem.acquire()
    return sem


# How many leading bytes of the system prompt to hash for prefix-cache analysis.
# Picked to cover the typical "stable prefix" segment of Director/NPC prompts
# (world setting + NPC descriptions + behavior rules) without including the
# variable suffix.
_PREFIX_HASH_BYTES = 1024

# Phase 2.B.1 — exception-class names treated as retriable transient errors.
# We match by class name (not isinstance) so we don't have to import openai /
# httpx / anthropic at module load time. 5xx APIStatusError is detected via
# a status_code attribute fallback.
_TRANSIENT_EXC_NAMES = frozenset(
    {
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "RateLimitError",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "RemoteProtocolError",
        "ServerDisconnectedError",
    }
)


def _system_prefix_signature(system: str | None) -> dict | None:
    if not system:
        return None
    encoded = system.encode("utf-8", errors="ignore")
    head = encoded[:_PREFIX_HASH_BYTES]
    return {
        "prefix_hash": hashlib.sha256(head).hexdigest()[:16],
        "prefix_bytes": len(head),
        "system_total_bytes": len(encoded),
    }


def _is_transient(exc: BaseException) -> bool:
    """Whether this exception is worth retrying within the same provider."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if exc.__class__.__name__ in _TRANSIENT_EXC_NAMES:
        return True
    # 5xx wrapped in provider-specific status errors
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if isinstance(status, int) and 500 <= status < 600:
        return True
    return False


class LLMRouter:
    def __init__(
        self,
        providers: dict[str, LLMProvider],
        fallback_chain: list[str] | None = None,
        identity: dict[str, str | None] | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        retry_backoff_seconds: float | None = None,
        reasoning: bool | None = None,
    ):
        self.providers = providers
        self.fallback_chain = fallback_chain or list(providers.keys())
        # Default thinking/reasoning control forwarded to every provider call.
        # ``None`` = model default; ``False`` = disable (set by resolve_slot_router
        # for realtime game-loop slots). Carried on the router (not per agent
        # call) so agent code and test fakes stay untouched.
        self._reasoning = reasoning
        # Optional identity stamping for usage events. ``identity`` may
        # carry ``provider_name`` (display) and ``model_id`` (full model
        # string) so downstream cost / analytics can resolve the slot
        # binding behind a turn. When unset, usage events flow through
        # unchanged.
        self.identity = dict(identity or {})
        # Phase 2.B.1 — first-token timeout + bounded retry. Resolved lazily
        # from settings so tests can construct routers without env.
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    def current_model_id(self) -> str:
        """Return the model_id this router is bound to.

        Used by Director (and other agents) to look up per-model capability
        and decide whether to dispatch to forced tool_use, JSON mode, or
        legacy auto tool_use. Falls back to the first provider's `.model`
        when identity is unset (legacy / test routers).
        """
        mid = self.identity.get("model_id")
        if mid:
            return str(mid)
        for provider in self.providers.values():
            inner = getattr(provider, "model", None)
            if inner:
                return str(inner)
        return ""

    async def stream_json(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 2048,
        provider_offset: int = 0,
    ) -> AsyncIterator[dict]:
        """Native JSON object mode via the first available provider.

        For routers bound to reasoning models, this is the preferred path
        (response_format=json_object, no tool plumbing). Provider-side
        fallback: see LLMProvider.stream_json default in llm/base.py.

        ``provider_offset`` rotates the chain's starting provider. A JSON-mode
        parse failure is not an exception (the stream completes, the text just
        isn't valid JSON), so it never trips the in-stream fallback below — the
        caller's retry must rotate providers itself by bumping this offset, so
        retry N lands on a different provider/key instead of re-hitting the one
        that just produced unparseable output.
        """
        # BUGS #20 — share the same global concurrency slot pool as
        # stream_with_tools so the cap applies across both code paths.
        sem = await _acquire_global_concurrency_slot()
        try:
            async for event in self._stream_json_inner(
                messages=messages, system=system, max_tokens=max_tokens,
                provider_offset=provider_offset,
            ):
                yield event
        finally:
            sem.release()

    async def _stream_json_inner(
        self,
        *,
        messages: list[dict],
        system: str | None,
        max_tokens: int,
        provider_offset: int = 0,
    ) -> AsyncIterator[dict]:
        chain = self.fallback_chain
        if provider_offset and chain:
            k = provider_offset % len(chain)
            chain = chain[k:] + chain[:k]
        for name in chain:
            provider = self.providers.get(name)
            if provider is None:
                continue
            stamped_provider_name = self.identity.get("provider_name")
            stamped_model_id = self.identity.get("model_id") or getattr(provider, "model", None)
            # Forward reasoning only when set, so providers / test fakes that
            # predate the kwarg keep working.
            json_kwargs: dict = {}
            if self._reasoning is not None:
                json_kwargs["reasoning"] = self._reasoning
            async for event in provider.stream_json(
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                **json_kwargs,
            ):
                if event.get("type") == "usage":
                    _log_reasoning_content_observed(
                        event,
                        provider=name,
                        provider_name=stamped_provider_name,
                        model_id=stamped_model_id,
                        reasoning_requested=self._reasoning,
                    )
                    if stamped_provider_name and not event.get("provider_name"):
                        event = {**event, "provider_name": stamped_provider_name}
                    if stamped_model_id and not event.get("model_id"):
                        event = {**event, "model_id": stamped_model_id}
                    ctx = _current_usage_context()
                    if ctx is not None:
                        _fire_and_forget_text_usage(event, ctx)
                    _accumulate_usage(event)
                yield event
            return
        raise RuntimeError("No LLM providers available")

    def _resolved_settings(self) -> tuple[float, int, float]:
        if (
            self._timeout_seconds is not None
            and self._max_retries is not None
            and self._retry_backoff_seconds is not None
        ):
            return (
                self._timeout_seconds,
                self._max_retries,
                self._retry_backoff_seconds,
            )
        from config import settings

        return (
            self._timeout_seconds
            if self._timeout_seconds is not None
            else float(settings.llm_call_timeout_seconds),
            self._max_retries
            if self._max_retries is not None
            else int(settings.llm_call_max_retries),
            self._retry_backoff_seconds
            if self._retry_backoff_seconds is not None
            else float(settings.llm_call_retry_backoff_seconds),
        )

    async def stream_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
        provider_name: str | None = None,
        max_tokens: int = 2048,
        response_format: dict | None = None,
        tool_choice: str | dict | None = None,
        reasoning: bool | None = None,
    ) -> AsyncIterator[dict]:
        # ``reasoning`` is a per-call override of the router-level ``self._reasoning``.
        # None = use the router default (slot binding); True/False = force on/off for
        # this call only. Used by generation planning steps (roster / ip extraction)
        # to re-enable CoT on a generation slot that's otherwise reasoning-off.
        # BUGS #20 — gate on global concurrency to keep bursts from
        # collapsing the provider connection pool.
        sem = await _acquire_global_concurrency_slot()
        try:
            async for event in self._stream_with_tools_inner(
                messages=messages,
                tools=tools,
                system=system,
                provider_name=provider_name,
                max_tokens=max_tokens,
                response_format=response_format,
                tool_choice=tool_choice,
                reasoning=reasoning,
            ):
                yield event
        finally:
            sem.release()

    async def _stream_with_tools_inner(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        system: str | None,
        provider_name: str | None,
        max_tokens: int,
        response_format: dict | None,
        tool_choice: str | dict | None,
        reasoning: bool | None = None,
    ) -> AsyncIterator[dict]:
        chain = [provider_name] if provider_name else []
        chain.extend(name for name in self.fallback_chain if name not in chain)

        signature = _system_prefix_signature(system)
        timeout_s, max_retries, backoff_s = self._resolved_settings()

        last_error: BaseException | None = None
        for name in chain:
            provider = self.providers.get(name)
            if provider is None:
                continue
            if signature is not None:
                logger.info(
                    "prompt.prefix_hash",
                    provider=name,
                    tool_count=len(tools),
                    response_format=(response_format or {}).get("type"),
                    **signature,
                )
            # Only forward optional params when set, so providers/test fakes
            # that predate the kwarg keep working.
            extra: dict = {}
            if response_format is not None:
                extra["response_format"] = response_format
            if tool_choice is not None:
                extra["tool_choice"] = tool_choice
            effective_reasoning = reasoning if reasoning is not None else self._reasoning
            if effective_reasoning is not None:
                extra["reasoning"] = effective_reasoning
            stamped_provider_name = self.identity.get("provider_name")
            stamped_model_id = self.identity.get("model_id") or getattr(provider, "model", None)

            yielded_any = False
            try:
                async for event in self._stream_one_provider(
                    provider=provider,
                    provider_name=name,
                    messages=messages,
                    tools=tools,
                    system=system,
                    max_tokens=max_tokens,
                    extra=extra,
                    timeout_s=timeout_s,
                    max_retries=max_retries,
                    backoff_s=backoff_s,
                ):
                    if event.get("type") == "usage":
                        _log_reasoning_content_observed(
                            event,
                            provider=name,
                            provider_name=stamped_provider_name,
                            model_id=stamped_model_id,
                            reasoning_requested=effective_reasoning,
                        )
                        # Don't clobber identity keys a provider already set;
                        # only fill in what's missing.
                        if stamped_provider_name and not event.get("provider_name"):
                            event = {**event, "provider_name": stamped_provider_name}
                        if stamped_model_id and not event.get("model_id"):
                            event = {**event, "model_id": stamped_model_id}
                        # AOP token recording: attribute this call to the
                        # ambient ``UsageContext``. Done after identity
                        # stamping so the sink sees provider_name/model_id.
                        # Imported lazily to dodge the top-level
                        # llm → services cycle.
                        ctx = _current_usage_context()
                        if ctx is not None:
                            _fire_and_forget_text_usage(event, ctx)
                        _accumulate_usage(event)
                    yielded_any = True
                    yield event
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "llm_provider_failed",
                    provider=name,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                if yielded_any:
                    # Partial output already streamed to the consumer.
                    # Falling back to the next provider would splice fresh
                    # full output onto the partial stream — propagate to
                    # the caller instead.
                    raise

        raise last_error or RuntimeError("No LLM providers available")

    async def _stream_one_provider(
        self,
        *,
        provider: LLMProvider,
        provider_name: str,
        messages: list[dict],
        tools: list[dict],
        system: str | None,
        max_tokens: int,
        extra: dict,
        timeout_s: float,
        max_retries: int,
        backoff_s: float,
    ) -> AsyncIterator[dict]:
        """Stream one provider with first-token timeout + bounded retry.

        Retry only happens BEFORE any event is yielded — once tokens start
        flowing we don't restart (the consumer has seen partial output).
        Non-transient errors (auth, malformed request, AppError) skip retry.
        """
        attempt = 0
        first_event: dict | None = None
        iterator = None

        while True:
            generator = provider.stream_with_tools(
                messages,
                tools,
                system,
                max_tokens=max_tokens,
                **extra,
            )
            iterator = generator.__aiter__()
            try:
                first_event = await asyncio.wait_for(
                    iterator.__anext__(),
                    timeout=timeout_s,
                )
                break
            except StopAsyncIteration:
                # Empty stream — treat as success, nothing to yield.
                return
            except asyncio.TimeoutError:
                logger.warning(
                    "llm.timeout",
                    provider=provider_name,
                    attempt=attempt,
                    timeout_seconds=timeout_s,
                )
                if attempt >= max_retries:
                    raise
                attempt += 1
                logger.info(
                    "llm.retry",
                    provider=provider_name,
                    attempt=attempt,
                    reason="timeout",
                )
                await asyncio.sleep(backoff_s)
                continue
            except Exception as exc:  # noqa: BLE001
                if attempt < max_retries and _is_transient(exc):
                    attempt += 1
                    logger.info(
                        "llm.retry",
                        provider=provider_name,
                        attempt=attempt,
                        reason=exc.__class__.__name__,
                        error=str(exc),
                    )
                    await asyncio.sleep(backoff_s)
                    continue
                raise

        # First event flowed — retries are no longer safe past this point
        # because the consumer may have been streamed partial output. We
        # still guard each subsequent chunk with ``timeout_s`` so a
        # provider that stops emitting mid-stream (no EOF, no error) is
        # surfaced as a TimeoutError instead of hanging the caller forever.
        if first_event is not None:
            yield first_event
        while True:
            try:
                event = await asyncio.wait_for(
                    iterator.__anext__(),
                    timeout=timeout_s,
                )
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError:
                logger.warning(
                    "llm.stream_stall",
                    provider=provider_name,
                    timeout_seconds=timeout_s,
                )
                raise
            yield event
