from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode

from config import settings

SENSITIVE_FIELDS = {
    "password",
    "api_key",
    "authorization",
    "cookie",
    "session",
    "x_admin_key",
    "x-admin-key",
}
FILTERED = "[Filtered]"


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in {field.replace("-", "_") for field in SENSITIVE_FIELDS}


def _scrub_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: FILTERED if _is_sensitive_key(str(key)) else _scrub_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item) for item in value)
    return value


def _scrub_query_string(query_string: Any) -> Any:
    if not isinstance(query_string, str) or not query_string:
        return query_string
    pairs = parse_qsl(query_string, keep_blank_values=True)
    if not pairs:
        return query_string
    if any(_is_sensitive_key(key) for key, _ in pairs):
        return FILTERED
    return urlencode(pairs)


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    scrubbed = _scrub_value(event)
    request = scrubbed.get("request")
    if isinstance(request, dict) and "query_string" in request:
        request["query_string"] = _scrub_query_string(request["query_string"])
    return scrubbed


def init_sentry() -> None:
    dsn = settings.backend_sentry_dsn or settings.sentry_dsn
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.environment,
        release=settings.release_tag or None,
        before_send=before_send,
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.0,
    )
