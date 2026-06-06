"""Two-pass case board (阶段二): case_board_ops moves out of the Director's main
JSON into a standalone call, so the heaviest payload no longer risks truncating
the narrative/ending. Flag-guarded (default off)."""
import pytest

from engine.director_agent import DirectorAgent
from engine.prompts import (
    _CASE_BOARD_OPS_ITEMS,
    build_case_board_ops_schema,
    build_director_tool_v2,
)


# ---- Task 5: shared schema constant ----
def test_case_board_ops_schema_uses_shared_items():
    schema = build_case_board_ops_schema()
    assert schema["properties"]["case_board_ops"]["items"] is _CASE_BOARD_OPS_ITEMS
    assert _CASE_BOARD_OPS_ITEMS["required"] == ["op_type", "path"]
    assert set(_CASE_BOARD_OPS_ITEMS["properties"]) == {
        "op_type", "path", "match", "value", "reason",
    }


# ---- Task 6: flag strips case_board_ops from the main schema ----
def test_two_pass_flag_strips_case_board_ops_from_v2_schema(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "director_case_board_two_pass", True)
    tool = build_director_tool_v2("mystery", "script", discovered_clue_ids=["c1"])
    assert "case_board_ops" not in tool["input_schema"]["properties"]


def test_single_pass_keeps_case_board_ops(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "director_case_board_two_pass", False)
    tool = build_director_tool_v2("mystery", "script", discovered_clue_ids=["c1"])
    assert "case_board_ops" in tool["input_schema"]["properties"]


# ---- Task 7: standalone generation ----
class _CaseBoardRouter:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = 0

    def current_model_id(self):
        return "deepseek-v4-pro"

    async def stream_json(self, messages, system=None, max_tokens=2048):
        self.calls += 1
        for c in self._chunks:
            yield {"type": "text_delta", "text": c}
        yield {"type": "usage", "input_tokens": 0, "output_tokens": 0,
               "finish_reason": "stop"}

    async def stream_with_tools(self, **kwargs):  # pragma: no cover
        if False:
            yield {}


@pytest.mark.asyncio
async def test_generate_case_board_ops_parses_ops():
    router = _CaseBoardRouter([
        '{"case_board_ops": [{"op_type": "set_field",',
        ' "path": ["current_objective"], "value": "找出真凶", "reason": "新线索"}]}',
    ])
    agent = DirectorAgent(router)
    ops = await agent.generate_case_board_ops(
        scene_brief="甄嬛发现账册", new_clues=["账册"],
        current_board={}, script_type="mystery", discovered_clue_ids=["账册"],
    )
    assert ops == [{
        "op_type": "set_field", "path": ["current_objective"],
        "value": "找出真凶", "reason": "新线索",
    }]


@pytest.mark.asyncio
async def test_generate_case_board_ops_empty_on_garbage():
    router = _CaseBoardRouter(["完全不是 json {{{"])
    agent = DirectorAgent(router)
    ops = await agent.generate_case_board_ops(
        scene_brief="x", new_clues=[], current_board={},
        script_type="mystery", discovered_clue_ids=[],
    )
    assert ops == []
