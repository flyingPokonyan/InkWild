"""Unit tests for semantic_review — BUGS #24."""
from __future__ import annotations

import pytest

from services.semantic_review import check_semantic_consistency


class _FakeRouter:
    def __init__(self, json_text: str):
        self._text = json_text

    async def stream_json(self, **_kwargs):
        # Mimic provider streaming: yield in chunks.
        for chunk in [self._text[: len(self._text) // 2], self._text[len(self._text) // 2 :]]:
            yield {"type": "text_delta", "text": chunk}


class _ExplodingRouter:
    async def stream_json(self, **_kwargs):
        raise RuntimeError("provider unavailable")
        yield  # pragma: no cover — make this an async generator


@pytest.mark.asyncio
async def test_returns_issues_when_llm_finds_inconsistency():
    router = _FakeRouter('{"issues": ["events [evt_1] 暗示 A 是凶手；结局 [bad_end] 揭露 B 才是真凶"]}')
    issues = await check_semantic_consistency(
        world={
            "characters": [{"name": "A"}, {"name": "B"}],
            "events_data": [{"id": "evt_1", "summary": "A 在暗处操纵"}],
        },
        script={
            "events_data": [],
            "endings_data": [
                {"id": "bad_end", "title": "真相揭晓", "description": "B 才是幕后黑手"}
            ],
        },
        llm_router=router,
    )
    assert len(issues) == 1
    assert "evt_1" in issues[0]


_MINIMAL_INPUT = {
    "world": {"events_data": [{"id": "e1", "summary": "x"}]},
    "script": {"endings_data": [{"id": "end_1", "title": "t"}]},
}


@pytest.mark.asyncio
async def test_returns_empty_when_clean():
    router = _FakeRouter('{"issues": []}')
    issues = await check_semantic_consistency(llm_router=router, **_MINIMAL_INPUT)
    assert issues == []


@pytest.mark.asyncio
async def test_returns_empty_on_llm_failure():
    issues = await check_semantic_consistency(llm_router=_ExplodingRouter(), **_MINIMAL_INPUT)
    assert issues == []


@pytest.mark.asyncio
async def test_tolerates_json_with_code_fence_prefix():
    router = _FakeRouter('```json\n{"issues": ["x"]}\n```')
    issues = await check_semantic_consistency(llm_router=router, **_MINIMAL_INPUT)
    assert issues == ["x"]


@pytest.mark.asyncio
async def test_short_circuits_without_endings():
    # No endings → nothing to compare → skip LLM entirely.
    router = _FakeRouter('{"issues": ["should not be reached"]}')
    issues = await check_semantic_consistency(
        world={"events_data": [{"id": "e1"}]},
        script={},
        llm_router=router,
    )
    assert issues == []


@pytest.mark.asyncio
async def test_short_circuits_without_events():
    router = _FakeRouter('{"issues": ["should not be reached"]}')
    issues = await check_semantic_consistency(
        world={},
        script={"endings_data": [{"id": "e"}]},
        llm_router=router,
    )
    assert issues == []
