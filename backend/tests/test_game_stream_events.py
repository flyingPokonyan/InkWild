import asyncio
import json

import pytest

from api.game import to_error_events, to_sse_event
from middleware.error_handler import AppError


def test_to_sse_event_serializes_processing_event():
    event = to_sse_event(
        {
            "type": "processing",
            "phase": "thinking",
            "focus_npcs": ["王福"],
            "flavor": "王福像是想起了什么",
        }
    )

    assert event["event"] == "processing"
    assert event["data"] == (
        '{"type": "processing", "version": 1, "phase": "thinking", "focus_npcs": ["王福"], '
        '"flavor": "王福像是想起了什么"}'
    )


def test_to_sse_event_rejects_internal_state_ready_event():
    with pytest.raises(ValueError, match="state_ready"):
        to_sse_event({"type": "state_ready", "new_state": object()})


def test_to_sse_event_error_with_string_code_passes_through():
    event = to_sse_event(
        {"type": "error", "code": "llm_timeout", "message": "LLM 调用超时"}
    )
    payload = json.loads(event["data"])
    assert payload["version"] == 1
    assert payload["code"] == "llm_timeout"
    assert payload["message"] == "LLM 调用超时"
    assert "legacy_code" not in payload


def test_to_sse_event_error_classifies_legacy_moderation_code():
    event = to_sse_event({"type": "error", "code": 40001, "message": "内容不合规"})
    payload = json.loads(event["data"])
    assert payload["code"] == "moderation"
    assert payload["legacy_code"] == 40001


def test_to_sse_event_error_classifies_legacy_provider_code():
    event = to_sse_event(
        {"type": "error", "code": 50001, "message": "LLM 服务暂时不可用"}
    )
    payload = json.loads(event["data"])
    assert payload["code"] == "provider_down"
    assert payload["legacy_code"] == 50001


def test_to_sse_event_error_classifies_unknown_legacy_code():
    event = to_sse_event(
        {"type": "error", "code": 40901, "message": "游戏状态已被更新，请刷新后重试"}
    )
    payload = json.loads(event["data"])
    assert payload["code"] == "unknown"
    assert payload["legacy_code"] == 40901


def test_to_sse_event_error_with_retry_after_ms():
    event = to_sse_event(
        {
            "type": "error",
            "code": "rate_limit",
            "message": "操作过于频繁",
            "retry_after_ms": 5000,
        }
    )
    payload = json.loads(event["data"])
    assert payload["code"] == "rate_limit"
    assert payload["retry_after_ms"] == 5000


def test_to_error_events_classifies_timeout_as_llm_timeout():
    events = to_error_events(asyncio.TimeoutError())
    assert len(events) == 2
    error_payload = json.loads(events[0]["data"])
    assert events[0]["event"] == "error"
    assert error_payload["code"] == "llm_timeout"
    assert events[1]["event"] == "done"


def test_to_error_events_classifies_connection_error_as_provider_down():
    class FakeConnectError(Exception):
        pass

    events = to_error_events(FakeConnectError("upstream gone"))
    error_payload = json.loads(events[0]["data"])
    assert error_payload["code"] == "provider_down"


def test_to_error_events_falls_back_to_unknown_for_generic_exception():
    events = to_error_events(RuntimeError("boom"))
    error_payload = json.loads(events[0]["data"])
    assert error_payload["code"] == "unknown"


def test_to_error_events_preserves_legacy_code_for_app_error():
    events = to_error_events(AppError(40001, "内容不合规"))
    error_payload = json.loads(events[0]["data"])
    assert error_payload["code"] == "moderation"
    assert error_payload["legacy_code"] == 40001
