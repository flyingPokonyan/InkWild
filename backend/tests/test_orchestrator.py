import pytest

from engine.director_agent import DirectorParseError, DirectorResult
from engine.orchestrator import Orchestrator
from engine.npc_agent import NPCResult
from engine.state_manager import GameState


class FakeDirectorAgent:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class FakeNPCAgent:
    def __init__(self):
        self.calls = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return NPCResult(npc_name=kwargs["npc_name"], dialogue=f'{kwargs["npc_name"]}: 好。')


class FakeNarratorAgent:
    def __init__(self, events, prelude_events=None):
        self.events = events
        self.prelude_events = prelude_events or []
        self.calls = []
        self.prelude_calls = []

    async def stream(self, **kwargs):
        self.calls.append(kwargs)
        for event in self.events:
            yield event

    async def stream_prelude(self, **kwargs):
        self.prelude_calls.append(kwargs)
        for event in self.prelude_events:
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
        "npcs": [
            {"name": "王福", "personality": "忠厚寡言", "secret": "他知道遗嘱。"},
            {"name": "赵姐", "personality": "热心", "secret": ""},
        ],
        "events": [],
        "endings": [],
    }


@pytest.mark.asyncio
async def test_orchestrator_full_pipeline():
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=["王福"],
            npc_instructions={"王福": "试探玩家。"},
            scene_direction="茶摊外起了风。",
            state_updates={"location": "茶摊", "time_advance": True, "quick_actions": ["继续观察"]},
            quick_actions=["继续观察"],
            ending_triggered=None,
            usage=None,
        )
    )
    npc_agent = FakeNPCAgent()
    narrator = FakeNarratorAgent(
        events=[
            {"type": "text_delta", "text": "你走向茶摊。"},
            {"type": "usage", "input_tokens": 10, "output_tokens": 5},
        ]
    )
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=npc_agent,
        narrator_agent=narrator,
    )

    events = []
    async for event in orchestrator.process_action(
        action_text="我去茶摊",
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
        memory_context="昨天见过王福。",
        authors_note="保持悬疑。",
    ):
        events.append(event)

    processing_events = [event for event in events if event.get("type") == "processing"]
    phase_sequence = [event["phase"] for event in processing_events]
    # Early-stream mode is on by default; the "thinking" hint is suppressed
    # because the narrator prelude already produces visible tokens.
    assert "directing" in phase_sequence
    assert "thinking" not in phase_sequence

    narrative_events = [event for event in events if event.get("type") == "narrative"]
    assert narrative_events == [{"type": "narrative", "text": "你走向茶摊。"}]

    state_update = next(event for event in events if event.get("type") == "state_update")
    assert state_update["game_state"]["current_location"] == "茶摊"
    assert events[-1]["type"] == "done"
    assert npc_agent.calls
    assert narrator.calls[0]["scene_direction"] == "茶摊外起了风。"


@pytest.mark.asyncio
async def test_orchestrator_skips_npc_agent_when_none_involved():
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=[],
            npc_instructions={},
            scene_direction="四周很安静。",
            state_updates={},
            quick_actions=["继续观察"],
            ending_triggered=None,
            usage=None,
        )
    )
    npc_agent = FakeNPCAgent()
    narrator = FakeNarratorAgent(events=[{"type": "text_delta", "text": "四周很安静。"}])
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=npc_agent,
        narrator_agent=narrator,
    )

    events = []
    async for event in orchestrator.process_action(
        action_text="我观察四周",
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="free",
    ):
        events.append(event)

    assert events[-1]["type"] == "done"
    assert npc_agent.calls == []


@pytest.mark.asyncio
async def test_orchestrator_applies_case_board_ops_in_script_mode():
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=[],
            npc_instructions={},
            scene_direction="血迹在门槛边延伸。",
            state_updates={},
            quick_actions=["检查门槛"],
            case_board_ops=[
                {
                    "op_type": "upsert_list_item",
                    "path": ["evidence"],
                    "match": {"clue_id": "clue_001"},
                    "value": {
                        "clue_id": "clue_001",
                        "category": "physical",
                        "related_suspect": "王福",
                    },
                    "reason": "血迹将门槛和王福联系起来。",
                }
            ],
            usage=None,
        )
    )
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=FakeNPCAgent(),
        narrator_agent=FakeNarratorAgent(events=[{"type": "text_delta", "text": "门槛边有暗红痕迹。"}]),
    )
    state = make_state()
    state.discovered_clues = [{"id": "clue_001", "content": "门槛血迹", "found_at": "第1天·上午"}]

    events = []
    async for event in orchestrator.process_action(
        action_text="我检查门槛",
        game_state=state,
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
    ):
        events.append(event)

    state_update = next(event for event in events if event["type"] == "state_update")
    assert state_update["game_state"]["case_board"]["evidence"] == [
        {"clue_id": "clue_001", "category": "physical", "related_suspect": "王福"}
    ]
    done_event = events[-1]
    assert done_event["case_board_history_entries"][0]["op_type"] == "upsert_list_item"


@pytest.mark.asyncio
async def test_orchestrator_rejects_invalid_case_board_ops_without_failing_turn():
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=[],
            npc_instructions={},
            scene_direction="线索还需要重新整理。",
            state_updates={},
            quick_actions=["继续观察"],
            case_board_ops=[
                {
                    "op_type": "upsert_list_item",
                    "path": ["evidence"],
                    "value": {"clue_id": "unknown"},
                }
            ],
            usage=None,
        )
    )
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=FakeNPCAgent(),
        narrator_agent=FakeNarratorAgent(events=[{"type": "text_delta", "text": "你暂时按下疑问。"}]),
    )

    events = []
    async for event in orchestrator.process_action(
        action_text="我整理线索",
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
    ):
        events.append(event)

    assert any(event == {"type": "narrative", "text": "你暂时按下疑问。"} for event in events)
    state_update = next(event for event in events if event["type"] == "state_update")
    assert state_update["game_state"]["case_board"] == {}
    assert events[-1]["case_board_history_entries"] == []


@pytest.mark.asyncio
async def test_orchestrator_case_board_ops_can_reference_same_turn_new_clue():
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=[],
            npc_instructions={},
            scene_direction="门槛边的血迹刚刚显现。",
            state_updates={"new_clues": ["门槛血迹"]},
            quick_actions=["追查血迹"],
            case_board_ops=[
                {
                    "op_type": "upsert_list_item",
                    "path": ["evidence"],
                    "match": {"clue_id": "clue_001"},
                    "value": {"clue_id": "clue_001", "category": "physical"},
                }
            ],
            usage=None,
        )
    )
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=FakeNPCAgent(),
        narrator_agent=FakeNarratorAgent(events=[{"type": "text_delta", "text": "血迹新鲜。"}]),
    )

    events = []
    async for event in orchestrator.process_action(
        action_text="我检查门槛",
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
    ):
        events.append(event)

    state_update = next(event for event in events if event["type"] == "state_update")
    assert state_update["game_state"]["discovered_clues"][0]["id"] == "clue_001"
    assert state_update["game_state"]["case_board"]["evidence"] == [
        {"clue_id": "clue_001", "category": "physical"}
    ]


@pytest.mark.asyncio
async def test_orchestrator_does_not_pass_global_recent_messages_to_npc_agent():
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=["王福"],
            npc_instructions={"王福": "只根据自己的记忆回应。"},
            scene_direction="王福看向门外。",
            state_updates={},
            quick_actions=["继续观察"],
            ending_triggered=None,
            usage=None,
        )
    )
    npc_agent = FakeNPCAgent()
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=npc_agent,
        narrator_agent=FakeNarratorAgent(events=[{"type": "text_delta", "text": "王福沉默了一会儿。"}]),
    )

    async for _ in orchestrator.process_action(
        action_text="我询问王福",
        game_state=make_state(),
        recent_messages=[
            {"role": "user", "content": "我刚把秘密告诉了赵姐"},
            {"role": "assistant", "content": "赵姐答应保密。"},
        ],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
        memory_entries=[
            {"memory_type": "discovery", "content": "王福知道后门钥匙", "round_number": 2, "related_npc": "王福"},
            {"memory_type": "discovery", "content": "赵姐知道玩家身份", "round_number": 3, "related_npc": "赵姐"},
        ],
    ):
        pass

    assert npc_agent.calls[0]["recent_messages"] == []
    assert npc_agent.calls[0]["npc_memories"] == [
        {"memory_type": "discovery", "content": "王福知道后门钥匙", "round_number": 2, "related_npc": "王福"}
    ]


@pytest.mark.asyncio
async def test_orchestrator_emits_ending_event():
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=[],
            npc_instructions={},
            scene_direction="真相浮现。",
            state_updates={"time_advance": True},
            quick_actions=["指出凶手"],
            ending_triggered={"should_end": True, "ending_type": "good", "reason": "证据完整"},
            usage=None,
        )
    )
    narrator = FakeNarratorAgent(
        events=[
            {"type": "text_delta", "text": "你说出了真相。"},
            {"type": "usage", "input_tokens": 10, "output_tokens": 5},
        ]
    )
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=FakeNPCAgent(),
        narrator_agent=narrator,
    )

    world_data = make_world_data()
    world_data["endings"] = [
        {
            "id": "ending-1",
            "ending_type": "good",
            "title": "真相大白",
            "description": "你揭穿了凶手。",
            "priority": 10,
            "hard_conditions": None,
            "soft_conditions": "玩家准确指出凶手",
        }
    ]

    events = []
    async for event in orchestrator.process_action(
        action_text="我指出王福是真凶",
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=world_data,
        game_mode="script",
    ):
        events.append(event)

    ending_events = [event for event in events if event["type"] == "ending"]
    assert len(ending_events) == 1
    assert ending_events[0]["ending_type"] == "good"
    assert ending_events[0]["title"] == "真相大白"


@pytest.mark.asyncio
async def test_orchestrator_includes_schedule_and_world_pulse_in_director_context():
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=[],
            npc_instructions={},
            scene_direction="街上很安静。",
            state_updates={},
            quick_actions=["继续观察"],
            ending_triggered=None,
            usage=None,
        )
    )
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=FakeNPCAgent(),
        narrator_agent=FakeNarratorAgent(events=[{"type": "text_delta", "text": "街上很安静。"}]),
    )

    state = GameState(
        current_time="第3天·夜晚",
        current_location="客栈",
        player_inventory=[],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        visited_locations=["客栈"],
        time_index=14,
        round_number=12,
        rounds_since_last_clue=5,
    )
    world_data = make_world_data()
    world_data["npcs"][0]["initial_location"] = "茶摊"
    world_data["npcs"][0]["schedule"] = {"夜晚": "祠堂"}
    world_data["npcs"][1]["initial_location"] = "客栈"
    world_data["npcs"][1]["schedule"] = {}

    async for _ in orchestrator.process_action(
        action_text="我先回客栈休息",
        game_state=state,
        recent_messages=[],
        context_summary=None,
        world_data=world_data,
        game_mode="free",
    ):
        pass

    memory_context = director.calls[0]["memory_context"]
    assert "## NPC 当前位置" in memory_context
    assert "王福：当前在「祠堂」" in memory_context
    assert "赵姐：当前在「客栈」" in memory_context
    assert "世界不会等待玩家" in memory_context


@pytest.mark.asyncio
async def test_orchestrator_appends_stage_summary_instruction_for_free_mode():
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=[],
            npc_instructions={},
            scene_direction="夜色渐深。",
            state_updates={"time_advance": True},
            quick_actions=["继续探索"],
            ending_triggered=None,
            usage=None,
        )
    )
    narrator = FakeNarratorAgent(events=[{"type": "text_delta", "text": "夜色渐深。"}])
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=FakeNPCAgent(),
        narrator_agent=narrator,
    )
    state = GameState(
        current_time="第4天·深夜",
        current_location="诊所",
        player_inventory=[],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        visited_locations=["诊所"],
        time_index=19,
        round_number=24,
        rounds_since_last_clue=2,
        npc_intents={
            "陈医生": {"current_goal": "藏住病人", "urgency": 8},
            "李守夜": {"current_goal": "调查矿井", "urgency": 8},
            "赵姐": {"current_goal": "维持茶馆日常", "urgency": 3},
        },
        world_conflicts=[{"description": "镇上最近有人失踪"}],
        last_stage_summary_round=0,
    )

    events = []
    async for event in orchestrator.process_action(
        action_text="我再次追问陈医生",
        game_state=state,
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="free",
    ):
        events.append(event)

    assert "章节总结" in narrator.calls[0]["scene_direction"]
    state_update = next(event for event in events if event["type"] == "state_update")
    assert state_update["game_state"]["last_stage_summary_round"] == 25


# ---------------------------------------------------------------------------
# Phase 2.A.3 — malformed output handling (Director parse error + NPC failure)
# ---------------------------------------------------------------------------


class RaisingDirectorAgent:
    def __init__(self, exc: Exception):
        self.exc = exc
        self.calls = 0

    async def run(self, **kwargs):
        self.calls += 1
        raise self.exc


class FlakyNPCAgent:
    """Raises for a configured npc_name, returns normal NPCResult for others."""

    def __init__(self, fail_for: str):
        self.fail_for = fail_for
        self.calls: list[dict] = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["npc_name"] == self.fail_for:
            raise RuntimeError("simulated provider explosion")
        return NPCResult(
            npc_name=kwargs["npc_name"], dialogue=f'{kwargs["npc_name"]}: 好。'
        )


@pytest.mark.asyncio
async def test_orchestrator_emits_llm_parse_error_when_director_fails():
    director = RaisingDirectorAgent(DirectorParseError("no tool_use after 3 attempts"))
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=FakeNPCAgent(),
        narrator_agent=FakeNarratorAgent(events=[]),
    )

    events = []
    async for event in orchestrator.process_action(
        action_text="我观察四周",
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
    ):
        events.append(event)

    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1
    assert error_events[0]["code"] == "llm_parse"
    # Turn aborted cleanly: no narrative, no state_update.
    assert not any(e.get("type") == "narrative" for e in events)
    assert not any(e.get("type") == "state_update" for e in events)
    # Director was called exactly once (its own internal retry happened
    # inside director_agent.run, not in orchestrator).
    assert director.calls == 1


@pytest.mark.asyncio
async def test_orchestrator_appends_player_action_to_state_history():
    """Phase 1.B.5 — Director's typed player_action lands in
    game_state.player_actions, stamped with the round number, so NPCs can
    reference cross-turn player behavior next turn.
    """
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=[],
            npc_instructions={},
            scene_direction="夜风掠过茶摊。",
            state_updates={},
            quick_actions=["继续观察"],
            player_action={
                "action_type": "ask_about",
                "target_npc": "王福",
                "target": "遗嘱",
                "summary": "玩家又一次追问遗嘱",
            },
            usage=None,
        )
    )
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=FakeNPCAgent(),
        narrator_agent=FakeNarratorAgent(events=[{"type": "text_delta", "text": "..."}]),
    )
    state = make_state()
    state.round_number = 4
    state.player_actions = [
        {"round": 3, "action_type": "visit_location", "target": "茶摊", "target_npc": "", "summary": "玩家走到茶摊"},
    ]

    state_update = None
    async for event in orchestrator.process_action(
        action_text="王福，遗嘱在哪儿？",
        game_state=state,
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
        round_number=4,
    ):
        if event.get("type") == "state_update":
            state_update = event

    assert state_update is not None
    new_actions = state_update["game_state"]["player_actions"]
    # Old entry kept; new ask_about entry appended (stamped with this round).
    assert len(new_actions) == 2
    latest = new_actions[-1]
    assert latest["action_type"] == "ask_about"
    assert latest["target_npc"] == "王福"
    assert latest["summary"] == "玩家又一次追问遗嘱"
    # round = round_number passed to process_action (the turn being processed).
    assert latest["round"] == 4


@pytest.mark.asyncio
async def test_orchestrator_caps_player_action_history_at_limit():
    """Phase 1.B.5 — game_state.player_actions stays bounded at the
    PLAYER_ACTIONS_HISTORY_LIMIT cap so a long session can't blow up state.
    """
    from engine.state_manager import PLAYER_ACTIONS_HISTORY_LIMIT

    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=[],
            npc_instructions={},
            scene_direction="...",
            state_updates={},
            quick_actions=["继续观察"],
            player_action={"action_type": "wait", "summary": "玩家停下来观察"},
            usage=None,
        )
    )
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=FakeNPCAgent(),
        narrator_agent=FakeNarratorAgent(events=[{"type": "text_delta", "text": "."}]),
    )
    state = make_state()
    # Pre-fill at the cap so the new entry should evict the oldest.
    state.player_actions = [
        {"round": i, "action_type": "wait", "summary": f"old {i}", "target_npc": "", "target": ""}
        for i in range(PLAYER_ACTIONS_HISTORY_LIMIT)
    ]

    state_update = None
    async for event in orchestrator.process_action(
        action_text="我等一下。",
        game_state=state,
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
        round_number=PLAYER_ACTIONS_HISTORY_LIMIT,  # ensure new entry round != 0
    ):
        if event.get("type") == "state_update":
            state_update = event

    assert state_update is not None
    new_actions = state_update["game_state"]["player_actions"]
    assert len(new_actions) == PLAYER_ACTIONS_HISTORY_LIMIT
    # Oldest (round=0) should have been evicted; newest summary is appended.
    rounds = [a["round"] for a in new_actions]
    assert 0 not in rounds
    assert new_actions[-1]["summary"] == "玩家停下来观察"


@pytest.mark.asyncio
async def test_orchestrator_passes_recent_player_actions_to_npc_agent():
    """Phase 1.B.5 — NPC agent receives the typed player_action history so it
    can render the cross-turn awareness section."""
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=["王福"],
            npc_instructions={"王福": "敷衍。"},
            scene_direction="灯笼摇晃。",
            state_updates={},
            quick_actions=["继续观察"],
            player_action={
                "action_type": "confront",
                "target_npc": "王福",
                "summary": "玩家当面质问王福",
            },
            usage=None,
        )
    )
    npc_agent = FakeNPCAgent()
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=npc_agent,
        narrator_agent=FakeNarratorAgent(events=[{"type": "text_delta", "text": "..."}]),
    )
    state = make_state()
    state.round_number = 7
    state.player_actions = [
        {"round": 5, "action_type": "ask_about", "target_npc": "王福", "summary": "追问遗嘱"},
        {"round": 6, "action_type": "ask_about", "target_npc": "王福", "summary": "再问一次"},
    ]

    async for _ in orchestrator.process_action(
        action_text="王福你别躲！",
        game_state=state,
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
        round_number=7,
    ):
        pass

    assert npc_agent.calls
    forwarded = npc_agent.calls[0].get("recent_player_actions") or []
    # NPC sees both prior history AND this turn's freshly appended entry.
    # Director's `instruction` covers the qualitative side; player_actions
    # gives NPCs the typed/structured view including "what you're being
    # asked about right now" labelled as confront/ask_about/etc.
    summaries = [a.get("summary") for a in forwarded]
    assert "追问遗嘱" in summaries
    assert "再问一次" in summaries
    assert "玩家当面质问王福" in summaries


@pytest.mark.asyncio
async def test_orchestrator_continues_when_one_npc_fails():
    director = FakeDirectorAgent(
        DirectorResult(
            involved_npcs=["王福", "赵姐"],
            npc_instructions={"王福": "试探玩家。", "赵姐": "搭话。"},
            scene_direction="茶摊外起了风。",
            state_updates={},
            quick_actions=["继续观察"],
            ending_triggered=None,
            usage=None,
        )
    )
    npc_agent = FlakyNPCAgent(fail_for="王福")
    narrator = FakeNarratorAgent(
        events=[{"type": "text_delta", "text": "你听见赵姐打招呼。"}]
    )
    orchestrator = Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=npc_agent,
        narrator_agent=narrator,
    )

    events = []
    async for event in orchestrator.process_action(
        action_text="我去茶摊",
        game_state=make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
    ):
        events.append(event)

    # Turn finished cleanly (done event present, no error event).
    assert events[-1]["type"] == "done"
    assert not any(e.get("type") == "error" for e in events)
    # Both NPCs were attempted; only the failing one was swallowed.
    npc_names_called = [c["npc_name"] for c in npc_agent.calls]
    assert "王福" in npc_names_called and "赵姐" in npc_names_called
