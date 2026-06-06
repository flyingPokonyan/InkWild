"""Image-generation decorator that records ``token_usage`` rows.

Wraps an ``ImageGenerator`` so every successful ``generate_image`` call
attributes one row to the ambient ``UsageContext``. Cost is derived from
``provider_models.image_price_cents_per_image`` (admin-configurable), so
the count + admin pricing fully determines spend without any per-call
metadata from the image provider itself.
"""

from __future__ import annotations

import base64
from dataclasses import replace

from llm.base import ImageGenerator, ImageResult
from llm.usage_context import current_usage_accumulator, current_usage_context
from services.usage_recorder import fire_and_forget_image_usage


class MeteredImageGenerator(ImageGenerator):
    """Decorator that fires a sink call on every successful image gen.

    On failure (``generate_image`` raises), no row is written — we only
    bill for images the provider actually returned.
    """

    def __init__(
        self,
        inner: ImageGenerator,
        *,
        provider_name: str | None,
        model_id: str | None,
    ) -> None:
        self._inner = inner
        self._provider_name = provider_name
        self._model_id = model_id

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
    ) -> ImageResult:
        result = await self._inner.generate_image(
            prompt, aspect_ratio=aspect_ratio, resolution=resolution
        )
        ctx = current_usage_context()
        if ctx is not None:
            # Image rows always bucket into ``image_gen`` regardless of
            # which task wrapped this call. Identity (session_id /
            # task_id / user_id / phase) is inherited so admin can still
            # join image cost back to the originating task.
            image_ctx = replace(ctx, purpose="image_gen")
            fire_and_forget_image_usage(
                provider_name=self._provider_name,
                model_id=self._model_id,
                ctx=image_ctx,
                count=1,
            )
            acc = current_usage_accumulator()
            if acc is not None:
                acc.add(
                    provider_name=self._provider_name,
                    model_id=self._model_id,
                    image_count=1,
                )
        return result


# Raw bytes of a 1×1 transparent PNG. Returned as ``base64_data`` so
# ``save_generated_image_result`` takes the has_data path and writes a real
# file via the storage backend — avoiding the httpx download in the
# has_url path that doesn't accept ``data:`` URLs.
_MOCK_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class MockImageGenerator(ImageGenerator):
    """No-op image generator that returns raw 1×1 transparent PNG bytes.

    Activated by ``settings.mock_images`` so e2e / research harnesses can
    bypass real image providers without changing slot bindings. Returns
    bytes (not a URL) so the storage pipeline writes a normal file and
    downstream consumers receive a real storage URL.
    """

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
    ) -> ImageResult:
        return ImageResult(base64_data=_MOCK_PNG_BYTES, format="png", model="mock")


__all__ = ["MeteredImageGenerator", "MockImageGenerator"]
