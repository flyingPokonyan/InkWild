from __future__ import annotations

import asyncio

import structlog
from openai import APIConnectionError, APIStatusError, APITimeoutError, InternalServerError, RateLimitError

from llm.base import ImageResult
from llm.openai_compatible import OpenAICompatibleImageProvider
from services.image_storage import IMAGE_PLACEHOLDER_URL

logger = structlog.get_logger()

# Retry policy: at most 2 retries (3 attempts total) with backoff 0.5s, 2s.
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS: tuple[float, ...] = (0.5, 2.0)

# Errors worth retrying — network / timeout / 5xx / 429.
_TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
    asyncio.TimeoutError,
)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, _TRANSIENT_ERRORS):
        return True
    # 5xx wrapped in generic APIStatusError
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", 0) or 0
        return status >= 500
    return False


class SeedreamImageProvider(OpenAICompatibleImageProvider):
    def __init__(self, *, api_key: str, model: str, base_url: str):
        super().__init__(api_key=api_key, base_url=base_url.rstrip("/"), model=model)

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
    ) -> ImageResult:
        """Generate image with bounded retry on transient errors.

        Final failure does NOT raise — returns a placeholder URL so the
        creation pipeline can continue.
        """
        last_error: BaseException | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await super().generate_image(prompt, aspect_ratio, resolution)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                error_type = type(exc).__name__
                transient = _is_transient(exc)
                if not transient or attempt >= _MAX_ATTEMPTS:
                    break
                logger.warning(
                    "image_generation.retry",
                    attempt=attempt,
                    error_type=error_type,
                    aspect_ratio=aspect_ratio,
                    model=self.model,
                )
                await asyncio.sleep(_BACKOFF_SECONDS[attempt - 1])

        attempts = _MAX_ATTEMPTS if last_error and _is_transient(last_error) else 1
        logger.warning(
            "image_generation.failed",
            prompt=prompt[:200],
            attempts=attempts,
            error_type=type(last_error).__name__ if last_error else "unknown",
            final_error_message=str(last_error) if last_error else "",
        )
        return ImageResult(url=IMAGE_PLACEHOLDER_URL, model=self.model)
