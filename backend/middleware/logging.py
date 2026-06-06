import time
from collections.abc import Mapping
from typing import Any

import structlog

logger = structlog.get_logger()
FILTERED = "[Filtered]"
SENSITIVE_FIELDS = {
    "password",
    "api_key",
    "authorization",
    "cookie",
    "session",
    "x_admin_key",
    "x-admin-key",
}


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in {field.replace("-", "_") for field in SENSITIVE_FIELDS}


def scrub_log_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: FILTERED if _is_sensitive_key(str(key)) else scrub_log_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub_log_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_log_value(item) for item in value)
    return value


class LoggingMiddleware:
    """Pure ASGI logging middleware.

    Implemented at the ASGI layer (not as BaseHTTPMiddleware) because
    BaseHTTPMiddleware wraps the response body through anyio memory streams,
    which is known to break streaming responses like SSE — symptoms include
    events arriving in chunks, premature connection close, or worker stalls.
    See https://github.com/encode/starlette/issues/919.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_holder: dict[str, int] = {}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            logger.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_holder.get("status"),
                duration_ms=elapsed_ms,
            )
