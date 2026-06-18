"""Tests for script roster augmentation (反哺)."""
from __future__ import annotations

import json

import pytest

from schemas.character_v2 import Character
from schemas.ip_knowledge_pack import IPCharacter, IPKnowledgePack
from schemas.research_pack import IPCanon
from services import script_roster_augmentation as sra


def _ip_char(name: str, must_have: bool = False) -> IPCharacter:
    return IPCharacter(
        name=name,
        role_in_story="配角",
        relation_to_protagonist="旧识",
        traits=["谨慎"],
        must_have=must_have,
    )


def _ip_pack(names: list[str]) -> IPKnowledgePack:
    return IPKnowledgePack(
        ip_name="测试IP",
        ip_type="novel",
        fidelity_mode="strict",
        summary="x",
        characters=[_ip_char(n, must_have=(i == 0)) for i, n in enumerate(names)],
        places=[],
        factions=[],
        iconic_objects=[],
        key_events=[],
        tone_lingo=[],
        passages=[],
    )


class _FakeRouter:
    """Returns a fixed JSON selection from stream_with_tools."""

    def __init__(self, needed: list[str]):
        self._payload = json.dumps({"needed": needed})

    async def stream_with_tools(self, *, messages, tools, system, max_tokens):
        yield {"type": "text_delta", "text": self._payload}


def test_is_world_scoped_addition_canonical_only():
    pack = _ip_pack(["关羽", "张飞"])
    assert sra.is_world_scoped_addition("关羽", pack) is True
    assert sra.is_world_scoped_addition("路人甲", pack) is False
    assert sra.is_world_scoped_addition("关羽", None) is False


@pytest.mark.asyncio
async def test_no_ip_pack_returns_empty():
    out = await sra.augment_script_roster(
        world_characters=[],
        script_base={"name": "x"},
        outline="y",
        ip_pack=None,
        fidelity_mode="none",
        ip_canon=IPCanon(),
        research_passages=[],
        locations=[],
        llm_router=_FakeRouter(["关羽"]),
        max_additions=6,
    )
    assert out == []


@pytest.mark.asyncio
async def test_selects_canonical_excludes_existing_and_caps(monkeypatch):
    pack = _ip_pack(["关羽", "张飞", "赵云", "马超"])
    # World already has 张飞 — must be excluded from additions.
    world = [Character(name="张飞", personality="猛")]

    async def fake_build(roster_entries, **kwargs):
        return [Character(name=e.name, personality="p") for e in roster_entries]

    monkeypatch.setattr(sra, "build_characters_in_batches", fake_build)

    # selector returns one existing (张飞, must be dropped), valid ones, and a
    # non-canonical fabrication (must be dropped by the pool intersection).
    out = await sra.augment_script_roster(
        world_characters=world,
        script_base={"name": "桃园案", "script_setting": "真相"},
        outline="大纲",
        ip_pack=pack,
        fidelity_mode="strict",
        ip_canon=IPCanon(),
        research_passages=[],
        locations=["营帐"],
        llm_router=_FakeRouter(["张飞", "关羽", "赵云", "马超", "查无此人"]),
        max_additions=2,
    )
    names = [c.name for c in out]
    assert "张飞" not in names          # already in world
    assert "查无此人" not in names      # not canonical → gated out
    assert len(names) == 2              # capped at max_additions
    assert set(names) <= {"关羽", "赵云", "马超"}
    assert all(c.is_image_target is False for c in out)  # NPC-only
