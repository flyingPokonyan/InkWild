"""Router hook + image wrapper integration tests.

Verifies the two AOP cut-points actually fire the sink. We patch the
``fire_and_forget_*`` functions to capture calls (recording into the DB
itself is exercised separately by ``test_usage_context.py``).
"""

from __future__ import annotations

import asyncio

import pytest

from llm import router as router_module
from llm.base import ImageGenerator, ImageResult
from llm.router import LLMRouter
from llm.usage_context import UsageContext, usage_context
from services import metered_image_generator as mig_module


class _FakeProvider:
    """Yields one text_delta and one usage event, mirroring real providers."""

    model = "fake-model-x"

    def __init__(self) -> None:
        self.calls = 0

    async def stream_with_tools(
        self, messages, tools, system=None, max_tokens=2048, **_kwargs
    ):
        self.calls += 1
        yield {"type": "text_delta", "text": "ok"}
        yield {
            "type": "usage",
            "input_tokens": 100,
            "output_tokens": 25,
        }


class _CapturingImageProvider(ImageGenerator):
    def __init__(self) -> None:
        self.calls = 0

    async def generate_image(
        self, prompt: str, aspect_ratio: str = "1:1", resolution: str = "1k"
    ) -> ImageResult:
        self.calls += 1
        return ImageResult(url=f"https://example/img-{self.calls}.png", model="fake-img")


@pytest.mark.asyncio
async def test_router_fires_sink_when_context_set(monkeypatch) -> None:
    captured: list[tuple[dict, UsageContext]] = []

    def fake_fire(event, ctx):
        captured.append((event, ctx))

    monkeypatch.setattr(router_module, "_fire_and_forget_text_usage", fake_fire)

    provider = _FakeProvider()
    router = LLMRouter(
        providers={"fake": provider},
        fallback_chain=["fake"],
        identity={"provider_name": "FakeCo", "model_id": "fake-model-x"},
    )

    events: list[dict] = []
    with usage_context(purpose="game", session_id="s-123"):
        async for ev in router.stream_with_tools(
            messages=[{"role": "user", "content": "hi"}], tools=[]
        ):
            events.append(ev)

    # Stream still yields all events to the consumer.
    types = [e["type"] for e in events]
    assert "text_delta" in types
    assert "usage" in types

    # Sink fired exactly once, with the stamped event and the right ctx.
    assert len(captured) == 1
    fired_event, fired_ctx = captured[0]
    assert fired_event["type"] == "usage"
    assert fired_event["input_tokens"] == 100
    assert fired_event["output_tokens"] == 25
    # Router stamped identity.
    assert fired_event["provider_name"] == "FakeCo"
    assert fired_event["model_id"] == "fake-model-x"
    # Context is the one we set.
    assert fired_ctx.purpose == "game"
    assert fired_ctx.session_id == "s-123"


@pytest.mark.asyncio
async def test_router_does_not_fire_sink_without_context(monkeypatch) -> None:
    captured: list = []
    monkeypatch.setattr(
        router_module,
        "_fire_and_forget_text_usage",
        lambda event, ctx: captured.append((event, ctx)),
    )

    provider = _FakeProvider()
    router = LLMRouter(providers={"fake": provider}, fallback_chain=["fake"])

    async for _ev in router.stream_with_tools(messages=[], tools=[]):
        pass

    # No ambient context → no sink call.
    assert captured == []


@pytest.mark.asyncio
async def test_image_wrapper_fires_sink_on_success(monkeypatch) -> None:
    captured: list[dict] = []

    def fake_image_fire(*, provider_name, model_id, ctx, count):
        captured.append(
            {
                "provider_name": provider_name,
                "model_id": model_id,
                "ctx": ctx,
                "count": count,
            }
        )

    monkeypatch.setattr(
        mig_module, "fire_and_forget_image_usage", fake_image_fire
    )

    inner = _CapturingImageProvider()
    wrapped = mig_module.MeteredImageGenerator(
        inner, provider_name="Seedream", model_id="seedream-1.0"
    )

    with usage_context(purpose="image_gen", task_id="t-1"):
        result = await wrapped.generate_image("a black circle", aspect_ratio="1:1")

    assert result.url.endswith("img-1.png")
    assert inner.calls == 1
    assert len(captured) == 1
    fired = captured[0]
    assert fired["provider_name"] == "Seedream"
    assert fired["model_id"] == "seedream-1.0"
    assert fired["count"] == 1
    assert fired["ctx"].purpose == "image_gen"
    assert fired["ctx"].task_id == "t-1"


@pytest.mark.asyncio
async def test_image_wrapper_skips_sink_without_context(monkeypatch) -> None:
    captured: list = []
    monkeypatch.setattr(
        mig_module,
        "fire_and_forget_image_usage",
        lambda **kwargs: captured.append(kwargs),
    )

    inner = _CapturingImageProvider()
    wrapped = mig_module.MeteredImageGenerator(
        inner, provider_name="Seedream", model_id="seedream-1.0"
    )

    await wrapped.generate_image("a black circle")
    assert captured == []


@pytest.mark.asyncio
async def test_image_wrapper_overrides_parent_purpose_to_image_gen(monkeypatch) -> None:
    """When image gen runs inside a world_gen / script_gen task, the
    recorded row must still bucket into ``image_gen`` (identity is
    inherited)."""
    captured: list[dict] = []
    monkeypatch.setattr(
        mig_module,
        "fire_and_forget_image_usage",
        lambda **kwargs: captured.append(kwargs),
    )

    inner = _CapturingImageProvider()
    wrapped = mig_module.MeteredImageGenerator(
        inner, provider_name="Seedream", model_id="seedream-1.0"
    )

    with usage_context(purpose="world_gen", task_id="t-world-1", user_id="u-1"):
        await wrapped.generate_image("a cover image")

    assert len(captured) == 1
    fired_ctx = captured[0]["ctx"]
    # purpose is rewritten...
    assert fired_ctx.purpose == "image_gen"
    # ...but identity is inherited from the wrapping world_gen context.
    assert fired_ctx.task_id == "t-world-1"
    assert fired_ctx.user_id == "u-1"


@pytest.mark.asyncio
async def test_image_wrapper_does_not_fire_on_failure(monkeypatch) -> None:
    """If the underlying provider raises, no row should be billed."""
    captured: list = []
    monkeypatch.setattr(
        mig_module,
        "fire_and_forget_image_usage",
        lambda **kwargs: captured.append(kwargs),
    )

    class _BoomProvider(ImageGenerator):
        async def generate_image(self, prompt, aspect_ratio="1:1", resolution="1k"):
            raise RuntimeError("seedream down")

    wrapped = mig_module.MeteredImageGenerator(
        _BoomProvider(), provider_name="Seedream", model_id="seedream-1.0"
    )

    with usage_context(purpose="image_gen", task_id="t-1"):
        with pytest.raises(RuntimeError, match="seedream down"):
            await wrapped.generate_image("oops")

    assert captured == []
