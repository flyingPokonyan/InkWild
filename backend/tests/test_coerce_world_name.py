"""BUGS #16 — world name critic / truncator unit tests."""
from services.world_creator_agent_v2 import coerce_world_name


def test_passes_through_clean_short_name():
    assert coerce_world_name("沉霜寒夜", "一个寒夜的故事") == "沉霜寒夜"


def test_caps_oversized_name():
    long_name = "原创近未来心理悬疑互动世界完全版第三部"
    out = coerce_world_name(long_name, "完全不相关的描述")
    assert 2 <= len(out) <= 16


def test_rejects_description_prefix_as_name():
    description = "原创近未来心理悬疑互动世界。玩家登上一艘改造成研究站的破冰船……"
    bad_name = description[:30]
    assert coerce_world_name(bad_name, description) == "未命名世界"


def test_rejects_empty_returns_placeholder():
    assert coerce_world_name("", "anything") == "未命名世界"
    assert coerce_world_name("   ", "anything") == "未命名世界"


def test_strips_newlines_and_punctuation():
    out = coerce_world_name("沉霜寒夜。\n", "完全不同的描述")
    assert out == "沉霜寒夜"


def test_single_char_falls_back():
    # Too short — coerce to placeholder.
    assert coerce_world_name("城", "城里的故事") == "未命名世界"
