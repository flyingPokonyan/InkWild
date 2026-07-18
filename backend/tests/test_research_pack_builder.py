import json
from collections.abc import AsyncIterator

import pytest

from schemas.research_pack import IPCanon, Passage
from services.research_pack_builder import (
    build_research_pack,
    probe_ip_canon,
    slice_admin_note_to_passages,
)


# ---- slice_admin_note_to_passages ----


def test_short_description_one_passage():
    passages = slice_admin_note_to_passages("一段短描述", max_chars=600)
    assert len(passages) == 1
    assert passages[0].source == "admin_note"
    assert passages[0].text == "一段短描述"


def test_long_description_paragraph_split():
    long = "段落一。\n\n段落二。\n\n段落三。"
    passages = slice_admin_note_to_passages(long, max_chars=600)
    assert len(passages) == 3
    assert all(p.source == "admin_note" for p in passages)
    assert [p.text for p in passages] == ["段落一。", "段落二。", "段落三。"]


def test_oversize_paragraph_chunked():
    long = "x" * 1500
    passages = slice_admin_note_to_passages(long, max_chars=600)
    assert len(passages) == 3  # 600 / 600 / 300
    assert len(passages[0].text) == 600
    assert len(passages[1].text) == 600
    assert len(passages[2].text) == 300


def test_empty_string_returns_empty_list():
    assert slice_admin_note_to_passages("", max_chars=600) == []
    assert slice_admin_note_to_passages("   ", max_chars=600) == []


def test_unique_passage_ids():
    long = "段落一。\n\n段落二。\n\n段落三。"
    passages = slice_admin_note_to_passages(long, max_chars=600)
    ids = [p.id for p in passages]
    assert len(set(ids)) == len(ids)


# ---- probe_ip_canon ----


def _make_stream_response(text: str):
    """Return an async generator that yields a single text_delta event."""

    async def _gen(*args, **kwargs) -> AsyncIterator[dict]:
        yield {"type": "text_delta", "text": text}

    return _gen


class _FakeRouter:
    """Minimal fake of LLMRouter with stream_with_tools."""

    def __init__(self, response_text: str):
        self._response_text = response_text

    async def stream_with_tools(self, **kwargs) -> AsyncIterator[dict]:
        yield {"type": "text_delta", "text": self._response_text}


class _ErrorRouter:
    """Fake router that raises on stream_with_tools."""

    async def stream_with_tools(self, **kwargs) -> AsyncIterator[dict]:
        raise RuntimeError("LLM 5xx")
        # make this an async generator
        yield


@pytest.mark.asyncio
async def test_probe_ip_canon_returns_structured():
    payload = json.dumps(
        {"title_guesses": ["琅琊榜"], "canonical_names": ["梅长苏", "靖王"]}
    )
    fake_router = _FakeRouter(payload)

    canon = await probe_ip_canon("一个民国权谋世界，主角是梅长苏", llm_router=fake_router)
    assert isinstance(canon, IPCanon)
    assert "梅长苏" in canon.canonical_names
    assert "琅琊榜" in canon.title_guesses


@pytest.mark.asyncio
async def test_probe_ip_canon_handles_invalid_json():
    fake_router = _FakeRouter("not valid json")
    canon = await probe_ip_canon("desc", llm_router=fake_router)
    # 失败时返回空 canon，不抛错
    assert canon.canonical_names == []
    assert canon.title_guesses == []


@pytest.mark.asyncio
async def test_probe_ip_canon_handles_llm_exception():
    fake_router = _ErrorRouter()
    canon = await probe_ip_canon("desc", llm_router=fake_router)
    assert canon.canonical_names == []


@pytest.mark.asyncio
async def test_dedicated_ip_path_skips_duplicate_probe_and_summary():
    class Broker:
        summarize_calls = 0

        async def collect_passages(self, _request, *, max_chars):
            assert max_chars == 600
            return [Passage(id="web-1", text="原始证据", source="tavily")]

        async def summarize_passages(self, _passages):
            self.summarize_calls += 1
            return "不应调用"

    broker = Broker()
    pack = await build_research_pack(
        description="已确认的 IP",
        broker=broker,
        llm_router=_ErrorRouter(),
        max_passages=8,
        max_passage_chars=600,
        probe_canon=False,
        summarize=False,
    )
    assert broker.summarize_calls == 0
    assert pack.ip_canon == IPCanon()
    assert {p.source for p in pack.passages} == {"admin_note", "tavily"}
