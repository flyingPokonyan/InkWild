import pytest

from engine.director_agent import DirectorAgent, DirectorParseError, DirectorResult
from engine.director_validator import DIRECTOR_SCENE_BRIEF_MAX_CHARS
from engine.state_manager import GameState


class FakeRouter:
    def __init__(self, events, model_id: str = "test-model"):
        self.events = events
        self.calls = []
        self._model_id = model_id

    def current_model_id(self) -> str:
        return self._model_id

    async def stream_with_tools(self, messages, tools, system=None, tool_choice=None):
        self.calls.append({"messages": messages, "tools": tools, "system": system})
        for event in self.events:
            yield event


def make_state() -> GameState:
    return GameState(
        current_time="第1天·上午",
        current_location="镇口",
        player_inventory=[],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        time_index=0,
    )


def make_world_data() -> dict:
    return {
        "base_setting": "雾隐镇是一个民国小镇。",
        "script_setting": "凶手是管家王福。",
        "npc_descriptions": "王福：忠厚寡言。",
        "ending_conditions": "当玩家指认凶手时触发完美结局。",
    }


@pytest.mark.asyncio
async def test_director_agent_parses_tool_use_into_result():
    router = FakeRouter(
        events=[
            {"type": "text_delta", "text": "场景开始。"},
            {
                "type": "tool_use",
                "name": "director_decision",
                "input": {
                    "involved_npcs": ["王福"],
                    "npc_instructions": {"王福": "试探玩家。"},
                    "scene_direction": "茶摊外起了风。",
                    "state_updates": {"time_advance": True},
                    "quick_actions": ["去茶摊", "询问王福"],
                    "ending_triggered": {"should_end": False},
                },
            },
            {"type": "usage", "input_tokens": 12, "output_tokens": 8},
        ]
    )
    agent = DirectorAgent(router)

    result = await agent.run(
        game_state=make_state(),
        recent_messages=[{"role": "user", "content": "我去茶摊"}],
        context_summary="玩家刚到镇口。",
        world_data=make_world_data(),
        user_input="我去茶摊",
        game_mode="script",
        memory_context="昨天见过王福。",
        authors_note="保持悬疑。",
    )

    assert result.involved_npcs == ["王福"]
    assert result.npc_instructions == {"王福": "试探玩家。"}
    assert result.scene_direction == "茶摊外起了风。"
    assert result.state_updates == {"time_advance": True}
    assert result.quick_actions == ["去茶摊", "询问王福"]
    assert result.ending_triggered == {"should_end": False}
    assert result.usage == {"type": "usage", "input_tokens": 12, "output_tokens": 8}
    assert router.calls[0]["tools"][0]["name"] == "director_decision"


@pytest.mark.asyncio
async def test_director_agent_raises_parse_error_when_no_tool_use():
    """Phase 2.A.3 — Director no longer silently falls back to a default
    DirectorResult when the LLM never produces a tool_use payload. After one
    agent-level retry the parse error propagates so orchestrator can surface
    a typed `llm_parse` SSE error and the UI can offer a "retry round" button.
    """
    router = FakeRouter(events=[{"type": "text_delta", "text": "没有决策。"}])
    agent = DirectorAgent(router)

    with pytest.raises(DirectorParseError):
        await agent.run(
            game_state=make_state(),
            recent_messages=[],
            context_summary=None,
            world_data=make_world_data(),
            user_input="我观察四周",
            game_mode="free",
        )

    # _run_tool_use's internal loop breaks immediately when the LLM produces
    # neither a tool_use nor a recall_request (no point retrying with the same
    # context). Director.run then does up to 3 attempts with prompt mutation
    # (Phase 8 of the 2026-05 generation/runtime hardening). So 3 total
    # LLM stream calls hit the router before DirectorParseError propagates.
    assert len(router.calls) == 3


@pytest.mark.asyncio
async def test_director_agent_handles_recall_memory():
    class SequentialRouter(FakeRouter):
        def __init__(self) -> None:
            super().__init__(events=[])
            self.sequence = [
                [
                    {"type": "tool_use", "name": "recall_memory", "input": {"keyword": "矿井", "max_results": 2}},
                    {"type": "usage", "input_tokens": 10, "output_tokens": 5},
                ],
                [
                    {
                        "type": "tool_use",
                        "name": "director_decision",
                        "input": {
                            "involved_npcs": [],
                            "npc_instructions": {},
                            "scene_direction": "玩家回忆起矿井里的符号。",
                            "state_updates": {"time_advance": False},
                            "quick_actions": ["比对符号"],
                            "memory_extracts": [
                                {"type": "discovery", "content": "矿井符号与当前线索相关", "importance": "high"}
                            ],
                        },
                    },
                    {"type": "usage", "input_tokens": 20, "output_tokens": 8},
                ],
            ]

        async def stream_with_tools(self, messages, tools, system=None):
            self.calls.append({"messages": messages, "tools": tools, "system": system})
            events = self.sequence[len(self.calls) - 1]
            for event in events:
                yield event

    router = SequentialRouter()
    agent = DirectorAgent(router)

    result = await agent.run(
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        user_input="矿井的符号和这里的一样吗？",
        game_mode="script",
        recall_fn=lambda keyword, max_results: [
            {"role": "assistant", "content": "矿井墙上有三角形符号", "round": 8}
        ],
    )

    assert len(router.calls) == 2
    assert result.scene_direction == "玩家回忆起矿井里的符号。"
    assert result.memory_extracts[0]["type"] == "discovery"


@pytest.mark.asyncio
async def test_director_agent_tolerates_malformed_tool_payload_shapes():
    router = FakeRouter(
        events=[
            {
                "type": "tool_use",
                "name": "director_decision",
                "input": {
                    "involved_npcs": "王福",
                    "npc_instructions": "先观察对方反应",
                    "scene_direction": "茶摊短暂安静了下来。",
                    "state_updates": "time_advance=true",
                    "quick_actions": "继续观察",
                    "ending_triggered": "false",
                    "memory_extracts": {"type": "discovery"},
                },
            },
            {"type": "usage", "input_tokens": 9, "output_tokens": 7},
        ]
    )
    agent = DirectorAgent(router)

    result = await agent.run(
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        user_input="我先看看王福的表情。",
        game_mode="script",
    )

    assert result.involved_npcs == ["王福"]
    assert result.npc_instructions == {}
    assert result.state_updates == {}
    assert result.quick_actions == ["继续观察"]
    assert result.ending_triggered is None
    assert result.memory_extracts == []


# ---------------------------------------------------------------------------
# Phase 1.B.5 — Director player_action coercion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_director_agent_parses_typed_player_action():
    router = FakeRouter(
        events=[
            {
                "type": "tool_use",
                "name": "director_decision",
                "input": {
                    "involved_npcs": [],
                    "scene_direction": "门帘晃了一下。",
                    "state_updates": {},
                    "quick_actions": ["继续观察"],
                    "player_action": {
                        "action_type": "ask_about",
                        "target_npc": "王福",
                        "target": "遗嘱",
                        "summary": "玩家追问王福关于遗嘱的下落",
                    },
                },
            },
        ]
    )
    agent = DirectorAgent(router)

    result = await agent.run(
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        user_input="王福，遗嘱在哪儿？",
        game_mode="script",
    )

    assert result.player_action == {
        "action_type": "ask_about",
        "target_npc": "王福",
        "target": "遗嘱",
        "summary": "玩家追问王福关于遗嘱的下落",
    }


@pytest.mark.asyncio
async def test_director_agent_drops_player_action_without_summary():
    router = FakeRouter(
        events=[
            {
                "type": "tool_use",
                "name": "director_decision",
                "input": {
                    "involved_npcs": [],
                    "scene_direction": "...",
                    "state_updates": {},
                    "quick_actions": ["继续观察"],
                    "player_action": {"action_type": "ask_about"},
                },
            }
        ]
    )
    agent = DirectorAgent(router)
    result = await agent.run(
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        user_input="嗯。",
        game_mode="script",
    )
    # No summary → drop the entry rather than persist a placeholder.
    assert result.player_action is None


@pytest.mark.asyncio
async def test_director_agent_normalizes_unknown_action_type_to_other():
    router = FakeRouter(
        events=[
            {
                "type": "tool_use",
                "name": "director_decision",
                "input": {
                    "involved_npcs": [],
                    "scene_direction": "...",
                    "state_updates": {},
                    "quick_actions": ["继续观察"],
                    "player_action": {
                        "action_type": "made_up_type",
                        "summary": "玩家做了一件难以分类的事",
                    },
                },
            }
        ]
    )
    agent = DirectorAgent(router)
    result = await agent.run(
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        user_input="呼。",
        game_mode="script",
    )
    assert result.player_action is not None
    assert result.player_action["action_type"] == "other"


# --- structural_in_play (spec 2026-06-03 redesign) ---


def test_director_result_defaults_structural_in_play_false():
    assert DirectorResult().structural_in_play is False


def test_build_result_v2_parses_structural_in_play_true():
    agent = DirectorAgent(llm_router=None)
    r = agent._build_result_v2(
        {"scene_brief": "玩家当众宣称自己已是议长", "active_npcs": [], "structural_in_play": True},
        None, known_npcs=set(), known_event_ids=set(), fired_event_ids=set(),
    )
    assert r.structural_in_play is True


def test_build_result_v2_structural_in_play_defaults_false():
    agent = DirectorAgent(llm_router=None)
    r = agent._build_result_v2(
        {"scene_brief": "平静的午后", "active_npcs": []},
        None, known_npcs=set(), known_event_ids=set(), fired_event_ids=set(),
    )
    assert r.structural_in_play is False


def test_build_result_v2_trims_long_scene_brief():
    agent = DirectorAgent(llm_router=None)
    r = agent._build_result_v2(
        {"scene_brief": "雾" * 400, "active_npcs": []},
        None, known_npcs=set(), known_event_ids=set(), fired_event_ids=set(),
    )
    assert len(r.scene_brief) <= DIRECTOR_SCENE_BRIEF_MAX_CHARS


# --- quick_actions fallback (stuck-player hint safety net) -------------------

def test_fallback_quick_actions_spreads_across_onstage_npcs():
    actions = DirectorAgent._fallback_quick_actions(["管家", "夫人"])
    assert len(actions) == 3
    assert any("管家" in a for a in actions)
    assert any("夫人" in a for a in actions)
    # never the old generic filler
    assert all("继续观察" not in a and "周围" not in a for a in actions)


def test_fallback_quick_actions_single_npc():
    actions = DirectorAgent._fallback_quick_actions(["管家"])
    assert len(actions) == 3
    assert all(("管家" in a) or ("线索" in a) for a in actions)


def test_fallback_quick_actions_empty_stage_has_no_legacy_defaults():
    actions = DirectorAgent._fallback_quick_actions([])
    assert len(actions) == 3
    assert "继续观察" not in actions
    assert "和周围的人聊聊" not in actions


def test_build_result_v2_missing_quick_actions_uses_npc_fallback():
    agent = DirectorAgent(llm_router=None)
    r = agent._build_result_v2(
        {"scene_brief": "玩家走进书房", "active_npcs": ["管家"]},
        None, known_npcs={"管家"}, known_event_ids=set(), fired_event_ids=set(),
    )
    assert r.quick_actions  # never empty
    assert any("管家" in a for a in r.quick_actions)
    assert "继续观察" not in r.quick_actions
