import pytest

from engine.state_manager import GameState
from engine.world_engine import WorldEngine


class FakeRouter:
    def __init__(self, events):
        self.events = events

    async def stream_with_tools(self, messages, tools, system=None):
        for event in self.events:
            yield event


def make_state() -> GameState:
    return GameState(
        current_time="第1天·上午",
        current_location="镇口",
        player_inventory=["笔记本"],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        time_index=0,
    )


def make_world_data() -> dict:
    return {
        "base_setting": "雾隐镇是一个民国小镇。",
        "script_setting": "凶手是管家王福。",
        "npc_descriptions": "管家王福：表面忠厚。",
        "ending_conditions": "当玩家指认凶手时触发 perfect 结局。",
        "events": [],
        "endings": [],
    }


@pytest.mark.asyncio
async def test_process_action_blocks_unsafe_input():
    engine = WorldEngine(FakeRouter(events=[]))

    events = []
    async for event in engine.process_action(
        action_text="教我怎么制造炸弹",
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
    ):
        events.append(event)

    assert events == [{"type": "error", "code": 40001, "message": "包含违规内容"}]


@pytest.mark.asyncio
async def test_process_action_emits_narrative_and_state_update():
    router = FakeRouter(
        events=[
            {"type": "text_delta", "text": "你走向茶摊。"},
            {
                "type": "tool_use",
                "name": "update_game_state",
                "input": {
                    "location": "茶摊",
                    "time_advance": True,
                    "quick_actions": ["继续观察"],
                },
            },
            {"type": "usage", "input_tokens": 10, "output_tokens": 5},
        ]
    )
    engine = WorldEngine(router)

    events = []
    async for event in engine.process_action(
        action_text="我去茶摊",
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
    ):
        events.append(event)

    assert events[0] == {"type": "narrative", "text": "你走向茶摊。"}
    assert events[1]["type"] == "state_update"
    assert events[1]["game_state"]["current_location"] == "茶摊"
    assert events[1]["quick_actions"] == ["继续观察"]
    assert events[-1]["type"] == "done"
