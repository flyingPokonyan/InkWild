"""Unit tests for MemoryManager v2 recall helpers (§7.1).

find_relevant_lore / find_npc_shared_events / find_npc_rumors are synchronous
instance methods on MemoryManager — no DB or embedding service needed.
"""

from __future__ import annotations

import pytest

from engine.memory_manager import MemoryManager


@pytest.fixture
def mm() -> MemoryManager:
    return MemoryManager()


# ---- find_relevant_lore ----


def test_find_relevant_lore_empty_npc_knowledge(mm: MemoryManager):
    lore = {
        "dimensions": [
            {
                "key": "tech",
                "name": "技术",
                "content_blocks": [{"heading": "h", "body": "b"}],
            },
        ]
    }
    assert mm.find_relevant_lore([], lore) == []


def test_find_relevant_lore_empty_pack(mm: MemoryManager):
    assert mm.find_relevant_lore(["关于科技"], None) == []
    assert mm.find_relevant_lore(["关于科技"], {"dimensions": []}) == []


def test_find_relevant_lore_keyword_match_fallback(mm: MemoryManager):
    """Keyword matching returns blocks that contain NPC's knowledge terms."""
    lore = {
        "dimensions": [
            {
                "key": "tech_levels",
                "name": "技术等级",
                "content_blocks": [
                    {"heading": "AI 监管", "body": "全球禁止 AGI"},
                    {"heading": "脑机接口", "body": "Neuralink 普及"},
                ],
            },
            {
                "key": "factions",
                "name": "派系",
                "content_blocks": [
                    {"heading": "黑客组织", "body": "Anonymous 主导"},
                ],
            },
        ]
    }
    # NPC cares about "AI" and "黑客" themes
    blocks = mm.find_relevant_lore(["AI 黑客"], lore, top_k=3)
    assert len(blocks) >= 1
    headings = {b.get("heading") for b in blocks}
    assert headings & {"AI 监管", "黑客组织"}


def test_find_relevant_lore_top_k_respected(mm: MemoryManager):
    """top_k cap is honoured."""
    lore = {
        "dimensions": [
            {
                "key": "d1",
                "name": "D1",
                "content_blocks": [
                    {"heading": f"H{i}", "body": "test keyword same"}
                    for i in range(10)
                ],
            }
        ]
    }
    blocks = mm.find_relevant_lore(["keyword"], lore, top_k=2)
    assert len(blocks) <= 2


def test_find_relevant_lore_no_match_returns_empty(mm: MemoryManager):
    lore = {
        "dimensions": [
            {
                "key": "a",
                "name": "A",
                "content_blocks": [
                    {"heading": "something unrelated", "body": "completely unrelated text"}
                ],
            }
        ]
    }
    blocks = mm.find_relevant_lore(["xyz_totally_absent"], lore)
    assert blocks == []


def test_find_relevant_lore_block_contains_dim_metadata(mm: MemoryManager):
    """Returned blocks carry key and name from the parent dimension."""
    lore = {
        "dimensions": [
            {
                "key": "magic",
                "name": "魔法体系",
                "content_blocks": [
                    {"heading": "魔法禁忌", "body": "不允许时间魔法"},
                ],
            }
        ]
    }
    blocks = mm.find_relevant_lore(["魔法"], lore)
    assert len(blocks) == 1
    assert blocks[0]["key"] == "magic"
    assert blocks[0]["name"] == "魔法体系"
    assert blocks[0]["heading"] == "魔法禁忌"


# ---- find_npc_shared_events ----


def test_find_npc_shared_events_filters_by_involvement(mm: MemoryManager):
    events = [
        {
            "id": "e1",
            "title": "事件1",
            "summary": "...",
            "involved_npcs": ["A", "B"],
            "perceptions": {
                "A": {"knows": "全知", "believes": "", "feels": ""},
                "B": {"knows": "", "believes": "可能 A 在", "feels": "怀疑"},
            },
        },
        {
            "id": "e2",
            "title": "事件2",
            "summary": "...",
            "involved_npcs": ["B", "C"],
            "perceptions": {"B": {"knows": "k2", "believes": "", "feels": ""}},
        },
    ]
    a_events = mm.find_npc_shared_events("A", events)
    assert len(a_events) == 1
    assert a_events[0]["id"] == "e1"
    assert a_events[0]["knows"] == "全知"

    b_events = mm.find_npc_shared_events("B", events)
    assert len(b_events) == 2


def test_find_npc_shared_events_perceptions_missing(mm: MemoryManager):
    """perceptions[npc] missing → knows/believes/feels are empty strings."""
    events = [
        {
            "id": "e1",
            "title": "T",
            "summary": "S",
            "involved_npcs": ["A"],
            "perceptions": {},
        },
    ]
    out = mm.find_npc_shared_events("A", events)
    assert len(out) == 1
    assert out[0]["knows"] == ""
    assert out[0]["believes"] == ""
    assert out[0]["feels"] == ""


def test_find_npc_shared_events_no_leakage(mm: MemoryManager):
    """A's view must not contain B's perception content."""
    events = [
        {
            "id": "e1",
            "title": "T",
            "summary": "S",
            "involved_npcs": ["A", "B"],
            "perceptions": {
                "A": {"knows": "A_secret", "believes": "", "feels": ""},
                "B": {"knows": "B_secret", "believes": "", "feels": ""},
            },
        }
    ]
    a_view = mm.find_npc_shared_events("A", events)
    serialized = str(a_view)
    assert "A_secret" in serialized
    assert "B_secret" not in serialized


def test_find_npc_shared_events_empty(mm: MemoryManager):
    assert mm.find_npc_shared_events("A", None) == []
    assert mm.find_npc_shared_events("A", []) == []


def test_find_npc_shared_events_not_involved(mm: MemoryManager):
    """NPC not in involved_npcs → no events returned."""
    events = [
        {
            "id": "e1",
            "title": "T",
            "summary": "S",
            "involved_npcs": ["B", "C"],
            "perceptions": {},
        }
    ]
    assert mm.find_npc_shared_events("A", events) == []


# ---- find_npc_rumors ----


def test_find_npc_rumors_returns_knower_rumors(mm: MemoryManager):
    events = [
        {
            "id": "e1",
            "rumors": [
                {"text": "T1", "knower_npcs": ["A", "B"]},
                {"text": "T2", "knower_npcs": ["C"]},
            ],
        }
    ]
    a_rumors = mm.find_npc_rumors("A", events)
    assert "T1" in a_rumors
    assert "T2" not in a_rumors


def test_find_npc_rumors_excludes_triggered(mm: MemoryManager):
    events = [
        {"id": "e1", "rumors": [{"text": "T1", "knower_npcs": ["A"]}]},
        {"id": "e2", "rumors": [{"text": "T2", "knower_npcs": ["A"]}]},
    ]
    rumors = mm.find_npc_rumors("A", events, triggered_event_ids={"e1"})
    assert "T1" not in rumors
    assert "T2" in rumors


def test_find_npc_rumors_dedup(mm: MemoryManager):
    events = [
        {"id": "e1", "rumors": [{"text": "Same", "knower_npcs": ["A"]}]},
        {"id": "e2", "rumors": [{"text": "Same", "knower_npcs": ["A"]}]},
    ]
    rumors = mm.find_npc_rumors("A", events)
    assert rumors.count("Same") == 1


def test_find_npc_rumors_empty(mm: MemoryManager):
    assert mm.find_npc_rumors("A", None) == []
    assert mm.find_npc_rumors("A", []) == []


def test_find_npc_rumors_no_rumors_key(mm: MemoryManager):
    """Events without a 'rumors' key are silently skipped."""
    events = [{"id": "e1", "title": "T"}]
    assert mm.find_npc_rumors("A", events) == []


def test_find_npc_rumors_triggered_none_treated_as_empty_set(mm: MemoryManager):
    """triggered_event_ids=None should behave like an empty set."""
    events = [{"id": "e1", "rumors": [{"text": "R1", "knower_npcs": ["A"]}]}]
    rumors = mm.find_npc_rumors("A", events, triggered_event_ids=None)
    assert "R1" in rumors
