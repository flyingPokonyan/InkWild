"""v2 思考态进度反馈 + done-core / case_board follow-up。

覆盖 _process_action_v2 在 docs/plans/play-turn-loading-2026-05.md 下的新行为：
  - 思考态演进进度事件 received / reasoning / npcs_entering / writing 按里程碑发出
  - done 在正文流完 + core（state_updates/ending）就绪即触发，不等 director 的
    case_board 尾巴；case_board 作为 Phase-4 follow-up 在 done 之后补发
  - 无 partial 信号时回退到 await 完整 director（case_board inline，无 follow-up）

这些 fake 实现 v2 接口（director.run_v2 / npc.run_v2 / narrator.stream_v2），
填补既有 v1-only fake 在 v2-default 下无法覆盖 v2 主链路的空白。
"""

from __future__ import annotations

import asyncio

import pytest

from engine.director_agent import DirectorAgent, DirectorResult
from engine.npc_action import NPCAction
from engine.orchestrator import Orchestrator
from engine.state_manager import GameState

pytestmark = pytest.mark.asyncio


CASE_BOARD_OP = {
    "op_type": "upsert_list_item",
    "path": ["evidence"],
    "match": {"clue_id": "clue_001"},
    "value": {"clue_id": "clue_001", "category": "physical", "related_suspect": "王福"},
    "reason": "血迹将门槛和王福联系起来。",
}

ACTION_TEXT = "我走到门槛边仔细检查地上的血迹痕迹"


def make_state() -> GameState:
    return GameState(
        current_time="第1天·上午",
        current_location="镇口",
        player_inventory=[],
        discovered_clues=[{"id": "clue_001", "content": "门槛血迹", "found_at": "第1天·上午"}],
        npc_relations={},
        triggered_events=[],
        time_index=0,
    )


def make_world_data() -> dict:
    return {
        "base_setting": "雾隐镇是一个民国小镇。",
        "script_setting": "凶手是管家王福。",
        "script_type": "mystery",
        "npc_descriptions": "王福：忠厚寡言。",
        "ending_conditions": "当玩家指认凶手时触发完美结局。",
        "npcs": [
            {"name": "王福", "personality": "忠厚寡言", "secret": "他知道遗嘱。"},
            {"name": "赵姐", "personality": "热心", "secret": ""},
        ],
        "events": [],
        "events_data": [],
        "endings": [],
    }


def _full_result(*, with_case_board: bool, narrative_pressure: str = "advance") -> DirectorResult:
    return DirectorResult(
        involved_npcs=["王福"],
        scene_direction="门槛边有暗红痕迹。",
        state_updates={"location": "茶摊"},
        quick_actions=["检查门槛"],
        ending_triggered=None,
        case_board_ops=[CASE_BOARD_OP] if with_case_board else [],
        player_action={"action_type": "examine", "summary": "检查门槛"},
        scene_brief="玩家检查了门槛。",
        active_npcs=["王福"],
        per_npc_focus={"王福": "玩家在检查门槛"},
        scene_role={"王福": "primary"},
        dramatic_intensity="medium",
        narrative_pressure=narrative_pressure,
        usage=None,
    )


class StreamingDirectorV2:
    """run_v2 fake：按 schema 顺序分段调用 on_partial 模拟流式，再返回完整 result。

    case_board_ops 只在完整 result 里（partial 阶段从不携带），以验证 core 提取剔除
    case_board + Phase-4 follow-up。``tail_delay`` 让 run_v2 在 partial 发完后仍挂起
    一小会儿——模拟真实 streaming 里 director 的 case_board 尾巴还没流完、narrator
    已经能起笔的时序（否则同步 fake 会让 director_task 在主循环看到 narrator_ready
    之前就完成，绕过 core 路径）。
    """

    def __init__(self, *, full_result: DirectorResult, stream: bool = True, tail_delay: float = 0.02):
        self.full_result = full_result
        self.stream = stream
        self.tail_delay = tail_delay
        self.calls: list[dict] = []
        # The orchestrator builds the core DirectorResult from the partial
        # snapshot via the director agent's parser. In production that's the
        # real DirectorAgent; delegate to it here so the test exercises the real
        # validation (active_npcs / case_board coercion etc.).
        self._real = DirectorAgent(object())

    def _build_result_v2(self, *args, **kwargs):
        return self._real._build_result_v2(*args, **kwargs)

    async def run_v2(self, *, on_partial=None, **kwargs):
        self.calls.append(kwargs)
        r = self.full_result
        if self.stream and on_partial is not None:
            base = {
                "scene_brief": r.scene_brief,
                "active_npcs": list(r.active_npcs),
                "per_npc_focus": dict(r.per_npc_focus),
                "scene_role": dict(r.scene_role),
                "dramatic_intensity": r.dramatic_intensity,
            }
            on_partial(dict(base))  # active_npcs + 5-field → npcs_entering + partial_ready
            base["narrative_pressure"] = r.narrative_pressure
            base["scene_direction"] = r.scene_direction
            on_partial(dict(base))  # narrative_pressure + scene_direction → narrator_ready + writing
            base["state_updates"] = dict(r.state_updates or {})
            base["quick_actions"] = list(r.quick_actions)
            if r.ending_triggered is not None:
                base["ending_triggered"] = r.ending_triggered
            base["player_action"] = dict(r.player_action or {})
            on_partial(dict(base))  # player_action → core_ready (snapshot 不含 case_board_ops)
            # 让出控制权，使主循环在 director_task 完成前先看到 narrator_ready。
            await asyncio.sleep(self.tail_delay)
        return r


class FakeNPCAgentV2:
    def __init__(self):
        self.calls: list[str] = []

    async def run_v2(self, *, npc_name, **kwargs):
        self.calls.append(npc_name)
        return NPCAction(
            npc_name=npc_name, action_type="speak", dialogue=f"{npc_name}：好。", priority=5
        )


class FakeNarratorV2:
    def __init__(self, events):
        self.events = events
        self.calls: list[dict] = []

    async def stream_v2(self, **kwargs):
        self.calls.append(kwargs)
        for event in self.events:
            yield event


def _make_orch(director, npc_agent, narrator) -> Orchestrator:
    return Orchestrator(
        llm_router=object(),
        director_agent=director,
        npc_agent=npc_agent,
        narrator_agent=narrator,
    )


async def _run(orch, *, game_mode="script", state=None) -> list[dict]:
    events: list[dict] = []
    async for event in orch.process_action(
        action_text=ACTION_TEXT,
        game_state=state or make_state(),
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode=game_mode,
        db=None,
        session_id=None,
    ):
        events.append(event)
    return events


async def test_progress_milestones_emitted_in_order():
    orch = _make_orch(
        StreamingDirectorV2(full_result=_full_result(with_case_board=True)),
        FakeNPCAgentV2(),
        FakeNarratorV2(
            [
                {"type": "text_delta", "text": "门槛边有暗红痕迹。"},
                {"type": "usage", "input_tokens": 1, "output_tokens": 1},
            ]
        ),
    )
    events = await _run(orch)

    stages = [e["stage"] for e in events if e.get("type") == "processing"]
    assert stages == ["received", "reasoning", "npcs_entering", "writing"]

    reasoning = next(e for e in events if e.get("stage") == "reasoning")
    assert reasoning["input_summary"] and reasoning["input_summary"] in ACTION_TEXT

    npcs_ev = next(e for e in events if e.get("stage") == "npcs_entering")
    assert npcs_ev["npcs"] == ["王福"]

    # All progress events are stage-driven (no legacy flavor/phase templating).
    assert all(e.get("kind") == "progress" for e in events if e.get("type") == "processing")


class UpstreamErrorDirectorV2:
    """run_v2 raises an upstream/provider error (e.g. 402) rather than a parse
    failure — the orchestrator must surface it as a distinct error code, not
    the misleading ``llm_parse`` "导演无法解析"."""

    async def run_v2(self, **kwargs):
        from engine.director_agent import DirectorUpstreamError

        raise DirectorUpstreamError("402 Insufficient Balance")


async def test_director_upstream_error_not_mapped_to_llm_parse():
    orch = _make_orch(
        UpstreamErrorDirectorV2(),
        FakeNPCAgentV2(),
        FakeNarratorV2([{"type": "text_delta", "text": "x"}]),
    )
    events = await _run(orch)
    err = next(e for e in events if e.get("type") == "error")
    assert err["code"] == "provider_unavailable"
    assert err["code"] != "llm_parse"


async def test_compression_counter_stamped_before_state_snapshot():
    """The compaction debounce stamp (last_compressed_round) must land on
    new_state BEFORE the turn emits its state snapshot. The early-stream path
    commits at state_ready/state_update, so a stamp applied afterward is lost
    and compaction re-fires every round (counter stuck at 0)."""
    state = make_state()
    state.round_number = 21  # +1 during the turn → 22, past threshold(20)
    state.last_compressed_round = 0
    orch = _make_orch(
        StreamingDirectorV2(full_result=_full_result(with_case_board=False)),
        FakeNPCAgentV2(),
        FakeNarratorV2(
            [
                {"type": "text_delta", "text": "门槛边有暗红痕迹。"},
                {"type": "usage", "input_tokens": 1, "output_tokens": 1},
            ]
        ),
    )
    events = []
    async for ev in orch.process_action(
        action_text=ACTION_TEXT,
        game_state=state,
        recent_messages=[],
        context_summary=None,
        world_data=make_world_data(),
        game_mode="script",
        db=None,
        session_id="s1",
    ):
        events.append(ev)

    su = next(e for e in events if e["type"] == "state_update")
    assert su["game_state"]["round_number"] == 22
    assert su["game_state"]["last_compressed_round"] == 22


async def test_done_emitted_before_case_board_followup():
    orch = _make_orch(
        StreamingDirectorV2(full_result=_full_result(with_case_board=True)),
        FakeNPCAgentV2(),
        FakeNarratorV2([{"type": "text_delta", "text": "门槛边有暗红痕迹。"}]),
    )
    events = await _run(orch)
    types = [e["type"] for e in events]

    assert "done" in types and "case_board_update" in types
    # done unlocks the player BEFORE the case_board tail lands.
    assert types.index("done") < types.index("case_board_update")
    # state_update (player-visible state) precedes done too.
    assert types.index("state_update") < types.index("done")

    done = next(e for e in events if e["type"] == "done")
    # case_board deferred → not applied at done; mem-extract rides the follow-up.
    assert done["case_board_history_entries"] == []
    assert "mem_extract_input" not in done

    cb = next(e for e in events if e["type"] == "case_board_update")
    assert cb["case_board_history_entries"][0]["op_type"] == "upsert_list_item"
    assert cb["game_state"]["case_board"]["evidence"][0]["clue_id"] == "clue_001"
    assert cb["mem_extract_input"]["case_board_ops"] == [CASE_BOARD_OP]


async def test_early_narrator_receives_streamed_narrative_pressure():
    narrator = FakeNarratorV2([{"type": "text_delta", "text": "门槛边有暗红痕迹。"}])
    orch = _make_orch(
        StreamingDirectorV2(
            full_result=_full_result(
                with_case_board=False,
                narrative_pressure="build_tension",
            )
        ),
        FakeNPCAgentV2(),
        narrator,
    )
    events = await _run(orch)

    assert any(e.get("stage") == "writing" for e in events)
    assert narrator.calls[0]["narrative_pressure"] == "build_tension"


async def test_done_state_update_excludes_deferred_case_board():
    """The state_update emitted at done must NOT yet contain this turn's
    case_board ops — those land a beat later via case_board_update."""
    orch = _make_orch(
        StreamingDirectorV2(full_result=_full_result(with_case_board=True)),
        FakeNPCAgentV2(),
        FakeNarratorV2([{"type": "text_delta", "text": "门槛边有暗红痕迹。"}]),
    )
    events = await _run(orch)
    state_update = next(e for e in events if e["type"] == "state_update")
    # evidence not present yet (case_board untouched at done time)
    assert state_update["game_state"].get("case_board", {}).get("evidence") in (None, [])


async def test_no_partial_signal_falls_back_to_full_await():
    """Director that doesn't stream partials → no core snapshot → await the full
    result, apply case_board inline at done, emit NO follow-up (§8 fallback)."""
    orch = _make_orch(
        StreamingDirectorV2(full_result=_full_result(with_case_board=True), stream=False),
        FakeNPCAgentV2(),
        FakeNarratorV2([{"type": "text_delta", "text": "门槛边有暗红痕迹。"}]),
    )
    events = await _run(orch)
    types = [e["type"] for e in events]

    assert "done" in types
    assert "case_board_update" not in types
    done = next(e for e in events if e["type"] == "done")
    assert done["case_board_history_entries"][0]["op_type"] == "upsert_list_item"
    assert "mem_extract_input" in done  # fired from done in the fallback path

    # No streaming → only the immediate received + reasoning milestones.
    stages = [e.get("stage") for e in events if e.get("type") == "processing"]
    assert "received" in stages and "reasoning" in stages
    assert "npcs_entering" not in stages and "writing" not in stages


async def test_free_mode_has_no_case_board_followup():
    orch = _make_orch(
        StreamingDirectorV2(full_result=_full_result(with_case_board=False)),
        FakeNPCAgentV2(),
        FakeNarratorV2([{"type": "text_delta", "text": "风过镇口。"}]),
    )
    events = await _run(orch, game_mode="free")
    types = [e["type"] for e in events]

    assert "done" in types
    assert "case_board_update" not in types
    done = next(e for e in events if e["type"] == "done")
    assert "mem_extract_input" in done
