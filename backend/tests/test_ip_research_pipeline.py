"""Tests for IP research pipeline (grok 多角度并行研究架构，2026-06-22 重写)。"""
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from schemas.ip_knowledge_pack import IPCharacter, IPKnowledgePack
from schemas.research_pack import Passage
from services.ip_recognizer import IPRecognition
from services.ip_research_pipeline import (
    build_ip_knowledge_pack,
    _gather_via_grok_fanout,
    _merge_packs,
)


class FakeLLM:
    """Sequential text streamer — swallows reasoning/extra kwargs."""
    def __init__(self, *texts: str):
        self._texts = list(texts)
        self._idx = 0

    async def stream_with_tools(self, **_kwargs):
        text = self._texts[min(self._idx, len(self._texts) - 1)]
        self._idx += 1
        for ch in text:
            yield {"type": "text_delta", "text": ch}


def _pe(chars, must_have=None, summary="一段足够长的剧情概述用于测试覆盖。") -> str:
    """Build a pre-extract JSON with the given character names."""
    must = set(must_have or [])
    cj = ",".join(
        f'{{"name":"{n}","role_in_story":"角色","relation_to_protagonist":"x",'
        f'"traits":["t"],"must_have":{"true" if n in must else "false"},'
        f'"source_passage_ids":[]}}'
        for n in chars
    )
    return (
        f'{{"summary":"{summary}","characters":[{cj}],"places":[],"factions":[],'
        f'"iconic_objects":[],"key_events":[],"tone_lingo":[],"timeline":[]}}'
    )


class DispatchLLM:
    """Returns canned JSON by which system prompt the call uses (concurrency-safe)."""
    def __init__(self, *, preextract, ground=None,
                 missing='{"missing_characters":[],"missing_places":[]}'):
        self.preextract = preextract  # str | callable(user)->str
        self.ground = ground
        self.missing = missing
        self.calls = {"preextract": 0, "ground": 0, "missing": 0}

    async def stream_with_tools(self, *, messages, system, **_kwargs):
        user = messages[0]["content"] if messages else ""
        if "知识抽取助手" in system:  # pre-extract（注意它正文里也含"事实核查"，须先判这条）
            self.calls["preextract"] += 1
            text = self.preextract(user) if callable(self.preextract) else self.preextract
        elif "完整性" in system:
            self.calls["missing"] += 1
            text = self.missing
        else:  # ground（事实核查助手）
            self.calls["ground"] += 1
            text = self.ground if self.ground is not None else self.preextract
        for ch in text:
            yield {"type": "text_delta", "text": ch}


class FakeGrok:
    def __init__(self, text="演员A 饰演 甄嬛，演员B 饰演 皇后"):
        self.text = text
        self.calls = []

    async def web_search(self, query, max_tokens=2048):
        self.calls.append(query)
        return SimpleNamespace(text=self.text, citations=[])


# ---- guards ----

@pytest.mark.asyncio
async def test_pipeline_returns_empty_when_kind_is_original():
    rec = IPRecognition(kind="original", confidence=0.0)
    pack = await build_ip_knowledge_pack(rec, "strict", llm_router=FakeLLM(""), tavily=AsyncMock())
    assert pack.characters == []
    assert pack.ip_name == ""


@pytest.mark.asyncio
async def test_pipeline_returns_empty_when_no_ip_name():
    rec = IPRecognition(kind="known_ip", confidence=0.9, ip_name=None)
    pack = await build_ip_knowledge_pack(rec, "strict", llm_router=FakeLLM(""), tavily=AsyncMock())
    assert pack.characters == []


# ---- C2: 实体级 merge ----

def _ipchar(name, must_have=False, traits=None, story_arc=""):
    return IPCharacter(
        name=name, role_in_story="角色", relation_to_protagonist="x",
        traits=traits or [], must_have=must_have, story_arc=story_arc,
    )


def test_merge_packs_dedup_and_must_have_or():
    rec = IPRecognition(kind="known_ip", confidence=1.0, ip_name="测试", ip_type="tv")
    pack_a = IPKnowledgePack(
        ip_name="测试", ip_type="tv", fidelity_mode="none", summary="短",
        characters=[_ipchar("甄嬛", must_have=False, traits=["机敏"])],
        places=[], factions=[], iconic_objects=[], key_events=[], tone_lingo=[],
        passages=[], timeline=[],
    )
    pack_b = IPKnowledgePack(
        ip_name="测试", ip_type="tv", fidelity_mode="none", summary="长一点的概述",
        characters=[
            _ipchar("甄 嬛", must_have=True, traits=["机敏", "隐忍"], story_arc="成长弧"),
            _ipchar("华妃", must_have=True),
        ],
        places=[], factions=[], iconic_objects=[], key_events=[], tone_lingo=[],
        passages=[], timeline=[],
    )
    merged = _merge_packs([pack_a, pack_b], rec, "strict")
    names = sorted(c.name for c in merged.characters)
    assert names == ["华妃", "甄 嬛"] or names == ["华妃", "甄嬛"]  # 甄嬛 去重（空格规范化）
    assert len(merged.characters) == 2
    # must_have OR：甄嬛在 a=False/b=True → 合并后 True
    zhen = next(c for c in merged.characters if "甄" in c.name)
    assert zhen.must_have is True
    assert "隐忍" in zhen.traits  # 取信息更全的 b 记录
    assert merged.summary == "长一点的概述"  # 取最长
    assert merged.fidelity_mode == "strict"


# ---- C1: grok fan-out ----

@pytest.mark.asyncio
async def test_gather_via_grok_fanout_runs_4_axes():
    rec = IPRecognition(kind="known_ip", confidence=1.0, ip_name="甄嬛传", ip_type="tv")
    grok = FakeGrok()
    passages, names = await _gather_via_grok_fanout(rec, grok)
    assert len(grok.calls) == 4  # 四轴并发
    assert len(passages) == 4
    # 候选名跨轴并集去重（每轴同样返回甄嬛/皇后 → 去重后 2 个）
    assert set(names) == {"甄嬛", "皇后"}


@pytest.mark.asyncio
async def test_gather_via_grok_fanout_no_provider_returns_empty():
    rec = IPRecognition(kind="known_ip", confidence=1.0, ip_name="甄嬛传", ip_type="tv")
    passages, names = await _gather_via_grok_fanout(rec, None)
    assert passages == [] and names == []


# ---- pipeline 集成 ----

@pytest.mark.asyncio
async def test_pipeline_merges_per_axis_preextract_union():
    """四轴 pre-extract 各挖一片 → merge 并集（无 grok，pack=merged candidates）。"""
    rec = IPRecognition(kind="known_ip", confidence=1.0, ip_name="甄嬛传", ip_type="tv")

    def pe_by_focus(user: str) -> str:
        if "对立" in user:
            return _pe(["华妃", "皇后"], must_have=["华妃", "皇后"])
        if "外围" in user:
            return _pe(["苏培盛", "崔槿汐", "温实初", "流朱"])
        if "设定" in user:
            return _pe([])  # 世界轴不出角色
        return _pe(["甄嬛", "沈眉庄"], must_have=["甄嬛"])

    llm = DispatchLLM(preextract=pe_by_focus)
    pack = await build_ip_knowledge_pack(rec, "strict", llm_router=llm, tavily=AsyncMock())
    names = {c.name for c in pack.characters}
    assert {"甄嬛", "沈眉庄", "华妃", "皇后", "苏培盛", "崔槿汐", "温实初", "流朱"} <= names
    assert set(pack.must_have_character_names()) == {"甄嬛", "华妃", "皇后"}
    assert llm.calls["preextract"] == 4  # 四轴并发


@pytest.mark.asyncio
async def test_pipeline_grounds_with_grok_passages():
    """有 grok passages 时走 ground；ground 输出替换 characters。"""
    rec = IPRecognition(kind="known_ip", confidence=1.0, ip_name="甄嬛传", ip_type="tv")
    ground_json = _pe(
        ["甄嬛", "华妃", "皇后", "沈眉庄", "安陵容", "苏培盛", "温实初"],
        must_have=["甄嬛", "华妃", "皇后"],
    )
    llm = DispatchLLM(preextract=_pe(["甄嬛", "华妃"], must_have=["甄嬛"]), ground=ground_json)
    pack = await build_ip_knowledge_pack(
        rec, "strict", llm_router=llm, tavily=AsyncMock(), grok_provider=FakeGrok(),
    )
    assert llm.calls["ground"] >= 1
    assert "安陵容" in {c.name for c in pack.characters}
    assert pack.fidelity_mode == "strict"


# ---- LLM 漂移鲁棒性（e2e 实测暴露）+ 名称变体归并 ----

def test_coerce_str_list_handles_dicts():
    from services.ip_research_pipeline import _coerce_str_list
    # tone_lingo 实测被 LLM 写成 [{"term":...}] → 须压成 str，否则 pydantic 炸
    assert _coerce_str_list(["甲", {"term": "一丈红"}, {"name": "x"}, 5, ""]) == ["甲", "一丈红", "x", "5"]


def test_prep_char_dicts_fills_missing_must_have():
    from services.ip_research_pipeline import _prep_char_dicts
    out = _prep_char_dicts([{"name": "温实初", "role_in_story": "挚友"}])
    assert out[0]["must_have"] is False  # 漏 must_have 不再被整条丢掉


@pytest.mark.asyncio
async def test_consolidate_merges_name_variants():
    from services.ip_research_pipeline import _consolidate_characters
    rec = IPRecognition(kind="known_ip", confidence=1.0, ip_name="甄嬛传", ip_type="tv")
    chars = [
        _ipchar("华妃"), _ipchar("年世兰", must_have=True),
        _ipchar("华妃（年世兰）"), _ipchar("端妃"),
    ]
    groups = (
        '{"groups":[{"canonical":"华妃（年世兰）","aliases":["华妃","年世兰","华妃（年世兰）"]},'
        '{"canonical":"端妃","aliases":["端妃"]}]}'
    )
    merged = await _consolidate_characters(chars, rec, FakeLLM(groups))
    names = sorted(c.name for c in merged)
    assert names == ["华妃（年世兰）", "端妃"]  # 三个变体合并为一
    hf = next(c for c in merged if "华妃" in c.name)
    assert hf.must_have is True  # must_have OR 合并


@pytest.mark.asyncio
async def test_consolidate_noop_on_llm_failure():
    from services.ip_research_pipeline import _consolidate_characters
    rec = IPRecognition(kind="known_ip", confidence=1.0, ip_name="x", ip_type="tv")
    chars = [_ipchar("甲"), _ipchar("乙")]
    merged = await _consolidate_characters(chars, rec, FakeLLM("不是JSON"))
    assert {c.name for c in merged} == {"甲", "乙"}  # 解析失败原样返回


@pytest.mark.asyncio
async def test_pipeline_underfilled_raises():
    """合并后 characters 低于按规模缩放的下限 → IPPackUnderfilledError。"""
    from services.ip_research_pipeline import IPPackUnderfilledError
    rec = IPRecognition(kind="known_ip", confidence=1.0, ip_name="冷门IP", ip_type="other")
    llm = DispatchLLM(preextract=_pe(["独苗"], must_have=["独苗"]))
    with pytest.raises(IPPackUnderfilledError):
        await build_ip_knowledge_pack(rec, "strict", llm_router=llm, tavily=AsyncMock())


@pytest.mark.asyncio
async def test_pre_extract_drops_malformed_timeline_entry_instead_of_raising():
    """Regression: 2026-05-19 大奉打更人 failure.

    LLM emitted a timeline entry with `description` instead of the required
    `event` field. The unguarded list comprehension raised ValidationError,
    aborted the whole pack construction, and the agent silently swallowed it —
    admin saw "ip_research completed" with ip_name=null and the world was
    generated with no canon anchors.

    The fix is `_safe_build_list`: a malformed entry is dropped with a warn,
    the rest of the pack survives.
    """
    from services.ip_research_pipeline import _pre_extract_canon

    rec = IPRecognition(kind="known_ip", confidence=1.0, ip_name="大奉打更人", ip_type="novel")
    # timeline[0] uses `description` (LLM drift) — used to kill the whole pack.
    # timeline[1] is well-formed — must survive.
    extract_json = (
        '{"summary":"打更人查案","characters":['
        '{"name":"许七安","role_in_story":"主角","relation_to_protagonist":"本人",'
        '"traits":[],"must_have":true,"source_passage_ids":[]}],'
        '"places":[],"factions":[],"iconic_objects":[],"key_events":[],'
        '"tone_lingo":[],'
        '"timeline":['
        '{"when":"中段","description":"卷入皇室内斗"},'
        '{"when":"结局","event":"许七安飞升"}'
        ']}'
    )
    pack = await _pre_extract_canon(rec, FakeLLM(extract_json))

    assert pack.ip_name == "大奉打更人"
    assert [c.name for c in pack.characters] == ["许七安"]
    # Bad timeline entry dropped, valid one preserved — no ValidationError raised.
    assert [t.event for t in pack.timeline] == ["许七安飞升"]
