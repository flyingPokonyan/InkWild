"""Tests for character_roster_builder — build_character_roster + build_characters_in_batches."""
import asyncio
import pytest
from unittest.mock import MagicMock

from schemas.research_pack import IPCanon, Passage
from schemas.character_v2 import Character, CharacterRosterEntry
from services.character_roster_builder import (
    build_character_roster,
    build_characters_in_batches,
)


def _make_router(responses: list[str]):
    call_idx = {"n": 0}
    fake = MagicMock()

    async def stream(*, messages, tools, system, max_tokens, reasoning=None):
        i = call_idx["n"]
        call_idx["n"] += 1
        call_idx["last_reasoning"] = reasoning
        yield {"type": "text_delta", "text": responses[i] if i < len(responses) else "{}"}

    fake.stream_with_tools = stream
    fake._calls = call_idx
    return fake


# ---- build_character_roster ----


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_roster_returns_entries():
    router = _make_router([
        '{"roster":[{"name":"梅长苏","role_tag":"主角","faction":"江左盟","is_image_target":true},'
        '{"name":"靖王","role_tag":"东宫","faction":"靖王党","is_image_target":true}]}'
    ])
    canon = IPCanon(canonical_names=["梅长苏", "靖王"])
    roster = await build_character_roster("一段权谋世界", "权谋", "古代", canon, [], [], router)
    assert len(roster) == 2
    assert roster[0].name == "梅长苏"
    assert roster[0].is_image_target is True


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_roster_handles_invalid_json():
    router = _make_router(["not json"])
    roster = await build_character_roster("x", "", "", IPCanon(), [], [], router)
    assert roster == []


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_roster_handles_llm_exception():
    fake = MagicMock()

    async def boom(*, messages, tools, system, max_tokens):
        raise RuntimeError("LLM 5xx")
        yield  # noqa: unreachable

    fake.stream_with_tools = boom
    roster = await build_character_roster("x", "", "", IPCanon(), [], [], fake)
    assert roster == []


# ---- build_characters_in_batches ----


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_batches_one_batch_for_few_npcs():
    roster = [CharacterRosterEntry(name=n, role_tag="r") for n in ["A", "B", "C"]]
    router = _make_router([
        '{"characters":['
        '{"name":"A","personality":"p1"},'
        '{"name":"B","personality":"p2"},'
        '{"name":"C","personality":"p3"}'
        ']}'
    ])
    chars = await build_characters_in_batches(
        roster, description="x", ip_canon=IPCanon(),
        locations=["loc1"], passages=[],
        llm_router=router, batch_size=6, concurrency=4,
    )
    assert len(chars) == 3
    assert {c.name for c in chars} == {"A", "B", "C"}
    assert router._calls["n"] == 1  # 只一批


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_batches_split_when_over_batch_size():
    roster = [CharacterRosterEntry(name=f"NPC{i}", role_tag="r") for i in range(13)]
    # 13 NPC，batch_size=5 → 3 批 (5+5+3)
    responses = [
        '{"characters":[' + ",".join([f'{{"name":"NPC{j}","personality":"p"}}' for j in range(0, 5)]) + ']}',
        '{"characters":[' + ",".join([f'{{"name":"NPC{j}","personality":"p"}}' for j in range(5, 10)]) + ']}',
        '{"characters":[' + ",".join([f'{{"name":"NPC{j}","personality":"p"}}' for j in range(10, 13)]) + ']}',
    ]
    router = _make_router(responses)
    chars = await build_characters_in_batches(
        roster, description="x", ip_canon=IPCanon(),
        locations=[], passages=[],
        llm_router=router, batch_size=5, concurrency=4,
    )
    assert len(chars) == 13
    assert {c.name for c in chars} == {f"NPC{i}" for i in range(13)}
    assert router._calls["n"] == 3


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_batches_extra_npc_dropped():
    """LLM 多产出 NPC（不在 roster）→ 丢弃 + warning。"""
    roster = [CharacterRosterEntry(name="A", role_tag="r"), CharacterRosterEntry(name="B", role_tag="r")]
    router = _make_router([
        '{"characters":['
        '{"name":"A","personality":"p"},'
        '{"name":"B","personality":"p"},'
        '{"name":"幽灵","personality":"不在 roster"}'
        ']}'
    ])
    chars = await build_characters_in_batches(
        roster, description="x", ip_canon=IPCanon(),
        locations=[], passages=[], llm_router=router,
    )
    names = {c.name for c in chars}
    assert names == {"A", "B"}
    assert "幽灵" not in names


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_batches_missing_npc_warn_no_placeholder():
    roster = [CharacterRosterEntry(name=n, role_tag="r") for n in ["A", "B", "C"]]
    router = _make_router([
        '{"characters":[{"name":"A","personality":"p"},{"name":"B","personality":"p"}]}'
    ])
    chars = await build_characters_in_batches(
        roster, description="x", ip_canon=IPCanon(),
        locations=[], passages=[], llm_router=router,
    )
    assert {c.name for c in chars} == {"A", "B"}
    # C 缺失，但产物不补占位（admin 看到不全可重跑）


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_batches_single_batch_failure_isolates():
    roster = [CharacterRosterEntry(name=f"N{i}", role_tag="r") for i in range(10)]
    fake = MagicMock()
    call_idx = {"n": 0}

    async def selective_fail(*, messages, tools, system, max_tokens):
        i = call_idx["n"]
        call_idx["n"] += 1
        if i == 0:
            yield {"type": "text_delta", "text":
                '{"characters":[' + ",".join([f'{{"name":"N{j}","personality":"p"}}' for j in range(5)]) + ']}'}
        else:
            raise RuntimeError("batch 2 failed")
            yield  # noqa: unreachable

    fake.stream_with_tools = selective_fail

    chars = await build_characters_in_batches(
        roster, description="x", ip_canon=IPCanon(),
        locations=[], passages=[], llm_router=fake,
        batch_size=5, concurrency=4,
    )
    assert {c.name for c in chars} == {f"N{i}" for i in range(5)}  # 第二批失败 5 个 NPC 都缺


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_batches_concurrent_within_limit():
    roster = [CharacterRosterEntry(name=f"N{i}", role_tag="r") for i in range(20)]
    fake = MagicMock()
    in_flight = {"now": 0, "max": 0}

    async def slow(*, messages, tools, system, max_tokens):
        in_flight["now"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["now"])
        await asyncio.sleep(0.02)
        in_flight["now"] -= 1
        yield {"type": "text_delta", "text": '{"characters":[]}'}

    fake.stream_with_tools = slow

    await build_characters_in_batches(
        roster, description="x", ip_canon=IPCanon(),
        locations=[], passages=[], llm_router=fake,
        batch_size=5, concurrency=2,  # 4 批，并发 2
    )
    assert in_flight["max"] <= 2


# ---- strict fidelity: 0 originals via post-prune ----

from schemas.ip_knowledge_pack import IPCharacter, IPKnowledgePack  # noqa: E402


def _ip_pack(names_must_have: list[tuple[str, bool]]) -> IPKnowledgePack:
    return IPKnowledgePack(
        ip_name="唐朝诡事录", ip_type="tv", fidelity_mode="strict", summary="s",
        characters=[
            IPCharacter(name=n, role_in_story="x", relation_to_protagonist="y", must_have=mh)
            for n, mh in names_must_have
        ],
        places=[], factions=[], iconic_objects=[], key_events=[],
        tone_lingo=[], passages=[], timeline=[],
    )


_MIXED_ROSTER = (
    '{"roster":['
    '{"name":"卢凌风 ","role_tag":"主角","is_image_target":true},'  # 带空格，规范化后命中
    '{"name":"苏无名","role_tag":"主角"},'
    '{"name":"裴喜君","role_tag":"配角"},'
    '{"name":"沈语","role_tag":"原创路人"},'      # 杜撰 -> 裁
    '{"name":"杜铭","role_tag":"原创工具人"}]}'    # 杜撰 -> 裁
)


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_strict_prunes_non_canon_characters():
    pack = _ip_pack([("卢凌风", True), ("苏无名", True), ("裴喜君", False)])
    roster = await build_character_roster(
        "探案", "悬疑", "唐", IPCanon(), [], [], _make_router([_MIXED_ROSTER]),
        ip_pack=pack, fidelity_mode="strict",
    )
    names = {e.name.strip() for e in roster}
    assert names == {"卢凌风", "苏无名", "裴喜君"}  # 3 canon 留，2 杜撰裁掉


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_loose_does_not_prune():
    pack = _ip_pack([("卢凌风", True), ("苏无名", True), ("裴喜君", False)])
    roster = await build_character_roster(
        "探案", "悬疑", "唐", IPCanon(), [], [], _make_router([_MIXED_ROSTER]),
        ip_pack=pack, fidelity_mode="loose",
    )
    assert len(roster) == 5  # loose 允许扩展，杜撰角色保留


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_strict_empty_canon_skips_prune():
    """研究完全失败（白名单空）时不裁，否则会裁成空 roster。"""
    pack = _ip_pack([])
    roster = await build_character_roster(
        "探案", "悬疑", "唐", IPCanon(), [], [], _make_router([_MIXED_ROSTER]),
        ip_pack=pack, fidelity_mode="strict",
    )
    assert len(roster) == 5


# ---- must_have 强制注入闭环（甄嬛传漏主角的修复） ----


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_strict_force_injects_dropped_must_have():
    """LLM 漏掉 must_have 角色（甄嬛传漏皇帝/华妃/皇后场景）→ _ensure_must_have 强制补回。"""
    # pack: 卢凌风/苏无名 must_have，裴喜君 optional；LLM 只吐了 卢凌风（漏了 苏无名）
    pack = _ip_pack([("卢凌风", True), ("苏无名", True), ("裴喜君", False)])
    only_one = '{"roster":[{"name":"卢凌风","role_tag":"主角","is_image_target":true}]}'
    roster = await build_character_roster(
        "探案", "悬疑", "唐", IPCanon(), [], [], _make_router([only_one]),
        ip_pack=pack, fidelity_mode="strict",
    )
    names = {e.name for e in roster}
    assert "苏无名" in names, "漏掉的 must_have 必须被强制补回"
    injected = next(e for e in roster if e.name == "苏无名")
    assert injected.is_image_target is True  # must_have 补回时设为可玩


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_loose_also_ensures_must_have():
    """loose 模式不裁但也要保证 must_have 在场。"""
    pack = _ip_pack([("卢凌风", True), ("苏无名", True)])
    only_one = '{"roster":[{"name":"卢凌风","role_tag":"主角"}]}'
    roster = await build_character_roster(
        "探案", "悬疑", "唐", IPCanon(), [], [], _make_router([only_one]),
        ip_pack=pack, fidelity_mode="loose",
    )
    assert "苏无名" in {e.name for e in roster}


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_roster_planning_runs_with_reasoning_on():
    """roster 规划步必须 per-call 打开 CoT（reasoning=True）。"""
    router = _make_router(['{"roster":[{"name":"梅长苏","role_tag":"主角"}]}'])
    await build_character_roster("权谋世界", "权谋", "古代", IPCanon(), [], [], router)
    assert router._calls["last_reasoning"] is True


# ---- critic 阶段确定性兜底：must_have 详情阶段丢失也补回 ----


@pytest.mark.no_db
def test_backfill_missing_must_have_appends_stub():
    from services.world_creator_agent_v2 import _backfill_missing_must_have

    pack = _ip_pack([("卢凌风", True), ("苏无名", True), ("裴喜君", False)])
    # world_characters 详情阶段只剩 卢凌风（苏无名 must_have 被批量阶段丢了）
    world_chars = [{"name": "卢凌风", "personality": "p", "role_tag": "主角"}]
    result, injected = _backfill_missing_must_have(world_chars, pack)
    assert injected == ["苏无名"]
    stub = next(c for c in result if c["name"] == "苏无名")
    assert stub["personality"]  # 必填字段非空
    assert stub["is_image_target"] is True
    # optional（裴喜君）不补
    assert "裴喜君" not in {c["name"] for c in result}


@pytest.mark.no_db
def test_backfill_noop_when_all_present():
    from services.world_creator_agent_v2 import _backfill_missing_must_have

    pack = _ip_pack([("卢凌风", True)])
    world_chars = [{"name": "卢凌风", "personality": "p"}]
    result, injected = _backfill_missing_must_have(world_chars, pack)
    assert injected == []
    assert len(result) == 1
