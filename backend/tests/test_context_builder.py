from engine.context_builder import (
    UPDATE_STATE_TOOL,
    build_messages,
    build_system_prompt,
    director_state_view,
)
from engine.state_manager import GameState


def test_build_system_prompt_script_mode():
    prompt = build_system_prompt(
        base_setting="雾隐镇是一个民国小镇...",
        script_setting="凶手是管家王福...",
        npc_descriptions="管家王福：表面忠厚...",
        ending_conditions="当玩家指认凶手时触发perfect结局",
        game_mode="script",
    )

    assert "雾隐镇" in prompt
    assert "凶手是管家王福" in prompt
    assert "update_game_state" in prompt


def test_build_system_prompt_no_script_in_free_mode():
    prompt = build_system_prompt(
        base_setting="雾隐镇是一个民国小镇...",
        script_setting="凶手是管家王福...",
        npc_descriptions="管家王福：表面忠厚...",
        ending_conditions="",
        game_mode="free",
    )

    assert "凶手是管家王福" not in prompt


def test_build_messages():
    state = GameState(
        current_time="第1天·下午",
        current_location="茶摊",
        player_inventory=["笔记本"],
        discovered_clues=[{"id": "c1", "content": "铜扣", "found_at": "上午"}],
        npc_relations={"管家": {"trust": 3, "mood": "正常", "last_interaction": ""}},
        triggered_events=["evt_001"],
        time_index=1,
    )
    recent_messages = [
        {"role": "user", "content": "我看看四周"},
        {"role": "assistant", "content": "你环顾四周..."},
    ]
    context_summary = "玩家刚到镇上，和茶摊老板闲聊了几句。"

    messages = build_messages(state, recent_messages, context_summary, "我去找管家")

    # Layout: [recent_messages..., context_summary + state dump, player_input].
    # Per-turn dynamic content is concentrated at the tail so the append-only
    # recent_messages prefix stays cacheable (see build_messages docstring).
    assert len(messages) == 4
    assert messages[0:2] == recent_messages
    assert "之前的经历" in messages[2]["content"]
    assert "【当前世界状态】" in messages[2]["content"]
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "<player_input>我去找管家</player_input>"


def test_director_state_view_caps_actions_and_drops_bookkeeping():
    state = GameState(
        current_time="第2天·上午",
        current_location="书房",
        discovered_clues=[{"id": "c1", "content": "带血的信封", "found_at": "上午"}],
        npc_relations={"管家": {"trust": 4, "mood": "紧张"}},
        narrative_arc={"stage": "rising"},
    )
    state.player_actions = [{"round": i, "summary": f"动作{i}"} for i in range(10)]
    state.offstage_event_log = {"管家": [{"round": 1, "content": "偷听"}]}
    state.pending_player_segments = ["残留指令"]
    state.last_active_round = {"管家": 5}
    state.triggered_event_ids = {"evt_001"}

    view = director_state_view(state)

    # player_actions capped to the recent tail (pacing signal, not the bulk)
    assert len(view["player_actions"]) == 3
    assert view["player_actions"][-1]["round"] == 9
    # runtime bookkeeping the Director never reads is omitted
    for key in (
        "offstage_event_log",
        "pending_player_segments",
        "last_active_round",
        "triggered_event_ids",
    ):
        assert key not in view
    # signal the Director acts on is retained
    assert view["discovered_clues"][0]["content"] == "带血的信封"
    assert view["npc_relations"]["管家"]["trust"] == 4
    assert view["narrative_arc"] == {"stage": "rising"}


def test_director_state_view_slims_info_items():
    # info_items is the single largest per-turn block (the Director never reads
    # the propagation matrix — info isolation is the NPC layer). The view drops
    # per-item ``known_by`` (→ ``known_count``) and tail-caps the list.
    state = GameState(current_time="第1天·上午", current_location="禁林")
    roster = [f"NPC{n}" for n in range(19)]
    state.info_items = [
        {
            "source": "Seamus",
            "content": f"线索{i}",
            "known_by": list(roster),
            "created_at_round": i,
        }
        for i in range(20)
    ]

    view = director_state_view(state)
    items = view["info_items"]

    # tail-capped to the most recent entries
    assert len(items) == 15
    assert items[-1]["content"] == "线索19"
    assert items[0]["content"] == "线索5"
    # known_by replaced with a count — no 19-name roster per item
    assert all("known_by" not in it for it in items)
    assert items[0]["known_count"] == 19
    assert items[0]["content"] == "线索5"  # content retained
    # view-only: persisted state untouched (NPC/world-sim still get full data)
    assert len(state.info_items) == 20
    assert state.info_items[0]["known_by"] == roster


def test_director_state_view_drops_empty_containers_keeps_scalars():
    state = GameState(current_time="第1天·上午", current_location="大堂")

    view = director_state_view(state)

    # empty list/dict fields carry no signal — dropped
    assert "discovered_clues" not in view
    assert "npc_relations" not in view
    assert "player_actions" not in view
    # scalar counters / required strings kept
    assert view["round_number"] == 0
    assert view["current_location"] == "大堂"


def test_build_messages_state_view_overrides_dump_and_is_compact():
    state = GameState(current_time="第1天·上午", current_location="大堂")
    state.player_actions = [{"round": i} for i in range(10)]

    messages = build_messages(
        state, [], None, "看看四周", state_view=director_state_view(state)
    )

    # no recent_messages / summary → [state dump, player_input]
    state_dump = messages[-2]["content"]
    # trimmed view: player_actions capped to 3, so the full round 9 tail is the
    # last entry and earlier rounds 0-6 are gone
    assert '"round":9' in state_dump
    assert '"round":6' not in state_dump
    # compact JSON — no indent whitespace
    assert "\n  " not in state_dump


def test_tool_definition_has_required_fields():
    assert UPDATE_STATE_TOOL["name"] == "update_game_state"
    props = UPDATE_STATE_TOOL["input_schema"]["properties"]
    assert "time_advance" in props
    assert "quick_actions" in props
    assert "ending_triggered" in props
