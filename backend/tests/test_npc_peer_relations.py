"""NPC-2 — persistent NPC↔NPC relations.

Covers the static path: seed at session start (both directions, asymmetry
preserved when explicit, trust clamped to [-10,10], invalid targets dropped),
the orchestrator-side query (A→? only — never reverse, never C↔D), the prompt
section render, and the LLM payload normalizer.
"""
from __future__ import annotations

import uuid

import pytest

from engine.memory_manager import MemoryManager
from engine.prompts import build_npc_system
from models.game import GameSession
from models.npc_relation import NPCRelation
from models.world import WorldCharacter
from services.game_service import GameService
from services.world_creator_agent import _normalize_peer_relations


class FakeDB:
    """Minimal collector for db.add() — _seed_npc_relations only needs add()."""
    def __init__(self):
        self.added: list = []

    def add(self, obj):
        self.added.append(obj)


def _wc(name: str, peer_relations=None) -> WorldCharacter:
    wc = WorldCharacter(
        id=str(uuid.uuid4()),
        world_id=str(uuid.uuid4()),
        name=name,
        personality="x",
        secret=None,
        knowledge=[],
        schedule={},
        initial_location="...",
    )
    wc.initial_peer_relations = peer_relations
    return wc


def _seed(npcs: list[WorldCharacter]) -> list[NPCRelation]:
    db = FakeDB()
    GameService(orchestrator=None)._seed_npc_relations(  # type: ignore[arg-type]
        db, session_id="00000000-0000-0000-0000-000000000001", npcs=npcs
    )
    return [obj for obj in db.added if isinstance(obj, NPCRelation)]


def test_seed_writes_both_directions_with_symmetric_default():
    """A declares relation to B; B declares nothing → both rows seeded with
    same trust/label/history."""
    npcs = [
        _wc("王福", peer_relations=[
            {"target": "赵姐", "trust": 6, "label": "邻居", "history_summary": "邻居 30 年"},
        ]),
        _wc("赵姐"),
    ]
    rows = _seed(npcs)
    by_pair = {(r.npc_a, r.npc_b): r for r in rows}
    assert ("王福", "赵姐") in by_pair
    assert ("赵姐", "王福") in by_pair
    assert by_pair[("王福", "赵姐")].trust == 6
    assert by_pair[("赵姐", "王福")].trust == 6  # symmetric backfill
    assert by_pair[("赵姐", "王福")].relationship_label == "邻居"


def test_seed_respects_explicit_asymmetry():
    """When B explicitly declares its own view of A, that wins over the
    symmetric backfill from A's side."""
    npcs = [
        _wc("A", peer_relations=[{"target": "B", "trust": 5, "label": "曾经的恩人"}]),
        _wc("B", peer_relations=[{"target": "A", "trust": -3, "label": "讨厌的人"}]),
    ]
    rows = _seed(npcs)
    by_pair = {(r.npc_a, r.npc_b): r for r in rows}
    assert by_pair[("A", "B")].trust == 5
    assert by_pair[("A", "B")].relationship_label == "曾经的恩人"
    assert by_pair[("B", "A")].trust == -3
    assert by_pair[("B", "A")].relationship_label == "讨厌的人"


def test_seed_clamps_trust_to_range():
    """LLM hallucinated trust=100 / -50 must be hard-clamped to [-10,10]."""
    npcs = [
        _wc("A", peer_relations=[
            {"target": "B", "trust": 100},
            {"target": "C", "trust": -50},
        ]),
        _wc("B"),
        _wc("C"),
    ]
    rows = _seed(npcs)
    by_pair = {(r.npc_a, r.npc_b): r for r in rows}
    assert by_pair[("A", "B")].trust == 10
    assert by_pair[("A", "C")].trust == -10


def test_seed_drops_targets_outside_npc_roster():
    """Targets that aren't in the NPC list (player character, hallucinated
    name, self-reference) are silently dropped."""
    npcs = [
        _wc("A", peer_relations=[
            {"target": "玩家"},      # not in roster
            {"target": "幽灵"},      # hallucinated
            {"target": "A"},         # self
            {"target": "B", "trust": 4},  # valid
        ]),
        _wc("B"),
    ]
    rows = _seed(npcs)
    by_pair = {(r.npc_a, r.npc_b): r for r in rows}
    # Only A↔B survives.
    assert set(by_pair.keys()) == {("A", "B"), ("B", "A")}


def test_seed_skips_when_no_relations_declared():
    """Empty / missing initial_peer_relations → no rows."""
    npcs = [_wc("A"), _wc("B")]
    assert _seed(npcs) == []


@pytest.mark.asyncio
async def test_get_npc_peer_relations_returns_only_outgoing(db):
    """Information isolation regression — A must only see A→? rows, never
    B→A (reverse trust) or B→C (unrelated)."""
    session = GameSession(
        user_id=str(uuid.uuid4()),
        world_id=str(uuid.uuid4()),
        character_id=str(uuid.uuid4()),
        mode="script",
        status="playing",
        game_state={},
        rounds_played=0,
    )
    db.add(session)
    await db.flush()

    rows = [
        NPCRelation(session_id=session.id, npc_a="A", npc_b="B", trust=6, relationship_label="朋友"),
        NPCRelation(session_id=session.id, npc_a="B", npc_b="A", trust=-2, relationship_label="冷淡"),
        NPCRelation(session_id=session.id, npc_a="B", npc_b="C", trust=8, relationship_label="兄弟"),
    ]
    for row in rows:
        db.add(row)
    await db.commit()

    result = await MemoryManager().get_npc_peer_relations(db, str(session.id), "A")

    assert len(result) == 1, f"A should only see A→? rows, got {result}"
    assert result[0]["target"] == "B"
    assert result[0]["trust"] == 6  # A's own view, not B's reverse trust
    # Reverse direction (B→A) and unrelated (B→C) MUST NOT leak.
    targets = {r["target"] for r in result}
    assert "C" not in targets


@pytest.mark.asyncio
async def test_get_npc_peer_relations_empty_when_no_rows(db):
    session = GameSession(
        user_id=str(uuid.uuid4()),
        world_id=str(uuid.uuid4()),
        character_id=str(uuid.uuid4()),
        mode="script",
        status="playing",
        game_state={},
        rounds_played=0,
    )
    db.add(session)
    await db.commit()

    result = await MemoryManager().get_npc_peer_relations(db, str(session.id), "孤独的人")
    assert result == []


def test_build_npc_system_renders_peer_relations_section():
    prompt = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚",
        npc_secret=None,
        instruction=".",
        peer_relations=[
            {"target": "赵姐", "trust": 6, "label": "邻居", "history_summary": "邻居 30 年常来借米"},
            {"target": "老爷", "trust": -3, "label": "雇主"},
        ],
    )
    assert "你跟身边人的关系" in prompt
    assert "赵姐" in prompt and "邻居" in prompt and "邻居 30 年常来借米" in prompt
    assert "老爷" in prompt and "雇主" in prompt
    # Trust value shown.
    assert "6/10" in prompt
    assert "-3/10" in prompt


def test_build_npc_system_skips_peer_relations_when_empty():
    """Empty / None peer_relations → section omitted (cache-friendly)."""
    for value in (None, [], [{"junk": "no target"}]):
        prompt = build_npc_system(
            npc_name="王福",
            npc_personality="忠厚",
            npc_secret=None,
            instruction=".",
            peer_relations=value,
        )
        assert "你跟身边人的关系" not in prompt


def test_normalize_peer_relations_helper():
    """world_creator_agent normalizer drops bad entries, clamps trust, and
    keeps optional fields only when non-empty."""
    raw = [
        {"target": "B", "trust": 100, "label": "  ", "history_summary": "ok"},  # clamp + drop blank label
        {"target": "  ", "trust": 5},                                            # blank target
        {"target": "C"},                                                         # default trust=0
        {"trust": 5},                                                            # missing target
        "not a dict",                                                            # wrong type
        {"target": "D", "trust": "not a number"},                                # bad trust
    ]
    out = _normalize_peer_relations(raw)
    assert out == [
        {"target": "B", "trust": 10, "history_summary": "ok"},
        {"target": "C", "trust": 0},
        {"target": "D", "trust": 0},
    ]


def test_normalize_peer_relations_handles_none_and_empty():
    assert _normalize_peer_relations(None) == []
    assert _normalize_peer_relations([]) == []
    assert _normalize_peer_relations("garbage") == []
