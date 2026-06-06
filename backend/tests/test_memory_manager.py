from engine.memory_manager import MemoryManager


def test_parse_memory_extracts():
    manager = MemoryManager()

    entries = manager.parse_memory_extracts(
        {
            "memory_extracts": [
                {"type": "player_claim", "content": "玩家说自己是记者", "importance": "high"},
                {"type": "npc_attitude", "content": "陈医生变得好奇", "importance": "medium"},
            ]
        },
        session_id="sess-1",
        round_number=5,
    )

    assert len(entries) == 2
    assert entries[0]["memory_type"] == "player_claim"
    assert entries[0]["importance"] == 8


def test_build_memory_context_and_search_messages():
    manager = MemoryManager()

    context = manager.build_memory_context(
        [
            {"memory_type": "player_claim", "content": "玩家说自己是记者", "round_number": 3},
            {"memory_type": "discovery", "content": "在矿井发现血迹", "round_number": 8},
        ]
    )
    results = manager.search_messages(
        [
            {"role": "user", "content": "我去矿井看看", "round": 3},
            {"role": "assistant", "content": "矿井里很暗", "round": 3},
            {"role": "assistant", "content": "陈医生在诊所", "round": 5},
        ],
        keyword="矿井",
        max_results=3,
    )

    assert "第3轮" in context
    assert "矿井" in context
    assert len(results) == 2


def test_filter_npc_memory_entries_returns_only_target_npc():
    manager = MemoryManager()

    entries = manager.filter_npc_memory_entries(
        [
            {"memory_type": "discovery", "content": "王福看到钥匙", "round_number": 2, "related_npc": "王福"},
            {"memory_type": "discovery", "content": "赵姐听到钟声", "round_number": 3, "related_npc": "赵姐"},
            {"memory_type": "global", "content": "所有人都知道起雾了", "round_number": 4, "related_npc": None},
        ],
        npc_name="王福",
    )

    assert entries == [
        {"memory_type": "discovery", "content": "王福看到钥匙", "round_number": 2, "related_npc": "王福"}
    ]
