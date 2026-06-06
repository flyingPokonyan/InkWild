from engine.prompts import build_world_pulse_directive
from engine.orchestrator import should_trigger_stage_summary
from engine.state_manager import GameState


def test_world_pulse_idle_player():
    state = GameState(
        current_time="第3天·夜晚",
        current_location="客栈",
        round_number=12,
        rounds_since_last_clue=5,
    )

    directive = build_world_pulse_directive(state, game_mode="script")
    assert "世界不会等待玩家" in directive
    assert "考虑让世界主动给出推动" in directive


def test_world_pulse_active_player():
    state = GameState(
        current_time="第1天·上午",
        current_location="镇口",
        round_number=2,
        rounds_since_last_clue=0,
    )

    directive = build_world_pulse_directive(state, game_mode="script")
    assert "当前节奏正常" in directive


def test_free_mode_stage_check_not_triggered():
    state = GameState(
        current_time="第1天·上午",
        current_location="镇口",
        round_number=5,
        npc_intents={"a": {"urgency": 8, "current_goal": "观察"}},
        last_stage_summary_round=0,
    )
    assert not should_trigger_stage_summary(state)


def test_free_mode_stage_check_triggered_once():
    state = GameState(
        current_time="第5天·夜晚",
        current_location="诊所",
        round_number=25,
        npc_intents={"a": {"urgency": 8, "current_goal": "调查诊所"}},
        world_conflicts=[{"description": "诊所有隐情"}],
        last_stage_summary_round=0,
    )
    assert should_trigger_stage_summary(state)

    state.last_stage_summary_round = 25
    assert not should_trigger_stage_summary(state)
