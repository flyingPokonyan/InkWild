"""lore_pack_builder 单元测试。

使用 fake LLMRouter（MagicMock + async generator），不发真实 LLM 请求。
"""
import pytest
from unittest.mock import MagicMock

from schemas.research_pack import IPCanon
from schemas.lore_pack import LorePack, LoreDimension
from services.lore_pack_builder import (
    build_lore_dimensions,
    build_lore_pack,
)


def _make_router(text_responses: list[str]):
    """构造 fake LLMRouter，每次 stream_with_tools 调用按顺序返回 text_responses 中的下一个"""
    call_count = {"n": 0}
    fake_router = MagicMock()

    async def fake_stream(*, messages, tools, system, max_tokens):
        idx = call_count["n"]
        call_count["n"] += 1
        text = text_responses[idx] if idx < len(text_responses) else "{}"
        yield {"type": "text_delta", "text": text}

    fake_router.stream_with_tools = fake_stream
    fake_router._call_count = call_count
    return fake_router


# ---- build_lore_dimensions ----

@pytest.mark.asyncio
async def test_dimensions_returns_list():
    router = _make_router(['{"dimensions":[{"key":"tech","name":"技术","why_relevant":"因为赛博朋克"}]}'])
    canon = IPCanon(title_guesses=["赛博朋克2077"])
    dims = await build_lore_dimensions("赛博朋克世界", "赛博朋克", "近未来", canon, router)
    assert len(dims) == 1
    assert dims[0].key == "tech"


@pytest.mark.asyncio
async def test_dimensions_empty_when_genre_simple():
    """题材不需要 lore（LLM 输出空）也应正常返回空 list。"""
    router = _make_router(['{"dimensions":[]}'])
    canon = IPCanon()
    dims = await build_lore_dimensions("校园日常", "日常", "现代", canon, router)
    assert dims == []


@pytest.mark.asyncio
async def test_dimensions_handles_invalid_json():
    router = _make_router(["not json"])
    dims = await build_lore_dimensions("x", "", "", IPCanon(), router)
    assert dims == []


@pytest.mark.asyncio
async def test_dimensions_handles_llm_exception():
    fake_router = MagicMock()

    async def boom(*, messages, tools, system, max_tokens):
        raise RuntimeError("LLM 5xx")
        yield  # 让它是 async generator

    fake_router.stream_with_tools = boom
    dims = await build_lore_dimensions("x", "", "", IPCanon(), fake_router)
    assert dims == []


# ---- build_lore_pack ----

@pytest.mark.asyncio
async def test_lore_pack_batches_all_dimensions_in_one_call():
    dims = [
        LoreDimension(key="tech", name="技术", why_relevant="why1"),
        LoreDimension(key="schools", name="门派", why_relevant="why2"),
    ]
    router = _make_router([
        '{"dimensions":['
        '{"key":"tech","content_blocks":[{"heading":"技术 H","body":"技术 B"}]},'
        '{"key":"schools","content_blocks":[{"heading":"门派 H","body":"门派 B"}]}'
        ']}'
    ])
    canon = IPCanon()

    pack = await build_lore_pack(
        dimensions=dims, description="x", ip_canon=canon, passages=[],
        llm_router=router, concurrency=4,
    )
    assert isinstance(pack, LorePack)
    assert len(pack.dimensions) == 2
    keys = {d.key for d in pack.dimensions}
    assert keys == {"tech", "schools"}
    assert pack.generated_at  # 非空
    assert router._call_count["n"] == 1


@pytest.mark.asyncio
async def test_lore_pack_missing_dimension_retry_isolates_failure():
    dims = [
        LoreDimension(key="ok", name="正常", why_relevant=""),
        LoreDimension(key="bad", name="坏", why_relevant=""),
    ]

    fake_router = MagicMock()
    call_idx = {"n": 0}

    async def selective_fail(*, messages, tools, system, max_tokens):
        idx = call_idx["n"]
        call_idx["n"] += 1
        if idx == 0:
            yield {
                "type": "text_delta",
                "text": (
                    '{"dimensions":[{"key":"ok","content_blocks":'
                    '[{"heading":"H","body":"B"}]}]}'
                ),
            }
        else:
            raise RuntimeError("LLM timeout")
            yield

    fake_router.stream_with_tools = selective_fail

    pack = await build_lore_pack(
        dimensions=dims, description="x", ip_canon=IPCanon(), passages=[],
        llm_router=fake_router, concurrency=4,
    )
    by_key = {d.key: d for d in pack.dimensions}
    assert len(by_key["ok"].content_blocks) == 1
    assert len(by_key["bad"].content_blocks) == 0  # 失败 → 空


@pytest.mark.asyncio
async def test_lore_pack_empty_dimensions_returns_empty_pack():
    pack = await build_lore_pack(
        dimensions=[], description="x", ip_canon=IPCanon(), passages=[],
        llm_router=MagicMock(),
    )
    assert pack.dimensions == []
    assert pack.generated_at  # 即使空也应 set timestamp


@pytest.mark.asyncio
async def test_lore_pack_retries_only_missing_dimensions_once():
    dims = [
        LoreDimension(key="a", name="A", why_relevant=""),
        LoreDimension(key="b", name="B", why_relevant=""),
    ]
    router = _make_router([
        '{"dimensions":[{"key":"a","content_blocks":[{"heading":"A","body":"A"}]}]}',
        '{"dimensions":[{"key":"b","content_blocks":[{"heading":"B","body":"B"}]}]}',
    ])
    pack = await build_lore_pack(
        dimensions=dims,
        description="x",
        ip_canon=IPCanon(),
        passages=[],
        llm_router=router,
        concurrency=2,
    )
    assert all(dim.content_blocks for dim in pack.dimensions)
    assert router._call_count["n"] == 2
