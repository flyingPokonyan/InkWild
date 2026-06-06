import json

import structlog

from engine.state_manager import GameState

logger = structlog.get_logger()

ENDING_SUMMARY_PROMPT = """\
你是一个游戏结局总结生成器。根据以下游戏数据，生成一份个性化的结局总结。

## 结局信息
- 结局类型: {ending_type}
- 结局标题: {ending_title}
- 剧本类型: {script_type}

## 案件面板
{case_board_json}

## 记忆上下文
{memory_context}

## 触发事件
{triggered_events}

## 游戏统计
- 总回合数: {total_rounds}
- 发现线索数: {clues_found}
- 游玩时长(分钟): {play_duration_minutes}

## 输出要求
请输出严格的 JSON（不要 markdown 代码块），包含以下字段：
- "ending_narrative": 200-400字个性化结局叙事，使用第三人称，回顾玩家的旅程并与结局呼应
- "path_review": 数组，包含5-8个关键节点，每个节点格式为 {{"time": "时间", "event": "事件名", "summary": "简述", "impact": "影响"}}
- "evidence_review": 仅当剧本类型为 mystery 时提供，格式为 {{"found": ["已发现线索"], "missed": ["遗漏线索"], "accuracy": 0.0到1.0的浮点数}}；非 mystery 类型时为 null
"""


async def generate_ending_summary(
    llm_router,
    ending: dict,
    game_state: GameState,
    memory_context: str,
    script_type: str,
    play_duration_minutes: int,
) -> dict:
    case_board = game_state.case_board or {}
    triggered = [e for e in (game_state.triggered_events or []) if e]
    clues_found = len(case_board.get("clues", []))

    prompt = ENDING_SUMMARY_PROMPT.format(
        ending_type=ending.get("ending_type", "unknown"),
        ending_title=ending.get("title", "未知结局"),
        script_type=script_type,
        case_board_json=json.dumps(case_board, ensure_ascii=False, indent=2) if case_board else "无",
        memory_context=memory_context or "无",
        triggered_events="、".join(triggered) if triggered else "无",
        total_rounds=game_state.round_number,
        clues_found=clues_found,
        play_duration_minutes=play_duration_minutes,
    )

    text_parts: list[str] = []
    try:
        async for event in llm_router.stream_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            system="你是一个游戏结局总结生成器。只输出 JSON，不要任何其他文本。",
            max_tokens=2048,
        ):
            if event.get("type") == "text_delta":
                text_parts.append(event.get("text", ""))

        raw = "".join(text_parts).strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("ending_summary_json_parse_failed", raw_text="".join(text_parts)[:200])
        return {
            "ending_narrative": f"故事在「{ending.get('title', '未知')}」中落下帷幕。",
            "path_review": [],
            "evidence_review": None,
        }
    except Exception:
        logger.warning("ending_summary_generation_failed", exc_info=True)
        return {
            "ending_narrative": f"故事在「{ending.get('title', '未知')}」中落下帷幕。",
            "path_review": [],
            "evidence_review": None,
        }


def check_hard_endings(endings: list[dict], state: GameState, game_mode: str = "script") -> dict | None:
    if game_mode == "free":
        return None

    matched = []

    for ending in endings:
        conditions = ending.get("hard_conditions")
        if not conditions:
            continue

        if _hard_condition_met(conditions, state):
            matched.append(ending)

    if not matched:
        return None

    return max(matched, key=lambda ending: ending.get("priority", 0))


def _hard_condition_met(conditions: dict, state: GameState) -> bool:
    condition_type = conditions.get("type")

    if condition_type == "time":
        return state.time_index > conditions["max_time_index"]

    if condition_type == "max_rounds":
        return state.round_number >= conditions["max_rounds"]

    if condition_type == "rounds_without_progress":
        return (
            state.rounds_since_last_clue >= conditions["min_rounds"]
            and state.round_number >= conditions.get("after_round", 0)
        )

    return False


# Phase 2.A.4 — when a stall forces an ending, prefer an honest "ran out of
# steam" outcome over a rewarding one (the player didn't earn `good`).
_STALL_ENDING_TYPE_PREFERENCE = ("timeout", "normal", "bad")


def check_forced_ending(
    endings: list[dict], state: GameState, game_mode: str = "script"
) -> dict | None:
    """Architectural safety floor — guarantees a SCRIPT session can't hang at
    climax forever even when no authored ``hard_conditions`` exist (every
    workshop-generated ending currently ships ``soft_conditions`` only, so
    ``check_hard_endings`` matches nothing).

    Fires on a *stall*: either N consecutive no-clue rounds past a floor round,
    or lingering in climax beyond a generous cap. This is not an absolute
    length cap — a player who keeps making real progress is never cut off.
    Free mode never forces (no ending exists there).
    """
    if game_mode == "free" or not endings:
        return None

    from engine.narrative_arc import (
        FORCED_AFTER_ROUND,
        FORCED_CLIMAX_LINGER_ROUNDS,
        FORCED_NO_PROGRESS_ROUNDS,
    )

    rounds_in_climax = int(getattr(state, "rounds_in_climax", 0) or 0)
    no_progress_stall = (
        state.rounds_since_last_clue >= FORCED_NO_PROGRESS_ROUNDS
        and state.round_number >= FORCED_AFTER_ROUND
    )
    climax_stall = rounds_in_climax >= FORCED_CLIMAX_LINGER_ROUNDS
    if not (no_progress_stall or climax_stall):
        return None

    return _pick_stall_ending(endings)


def _pick_stall_ending(endings: list[dict]) -> dict | None:
    by_type = {
        e.get("ending_type"): e for e in endings if isinstance(e, dict) and e.get("ending_type")
    }
    for ending_type in _STALL_ENDING_TYPE_PREFERENCE:
        if ending_type in by_type:
            return by_type[ending_type]
    # No preferred type present → fall back to the least-"earned" ending
    # (lowest priority), so a stall never hands out the best outcome.
    valid = [e for e in endings if isinstance(e, dict)]
    if not valid:
        return None
    return min(valid, key=lambda e: e.get("priority", 0))


def merge_ai_ending_judgment(endings: list[dict], ai_judgment: dict) -> dict | None:
    if not ai_judgment.get("should_end"):
        return None

    target_type = (ai_judgment.get("ending_type") or "").strip()
    for ending in endings:
        if (ending.get("ending_type") or "").strip() == target_type and ending.get("soft_conditions"):
            return ending

    # should_end=true but the Director's ending_type matched no soft ending.
    # This used to be a SILENT drop — the player's earned ending vanished and
    # they fell through to the stall consolation. Surface it so "director tried
    # to end but it was dropped" is observable (telemetry to verify the prompt /
    # arc fixes are landing). We deliberately do NOT auto-upgrade to some other
    # ending here (that would hand an unearned outcome); the stall floor still
    # guarantees the session can't hang.
    logger.warning(
        "ending.ai_judgment_unmatched",
        target_type=target_type,
        reason=ai_judgment.get("reason"),
        available_types=[
            (e.get("ending_type") or "").strip()
            for e in endings
            if isinstance(e, dict) and e.get("soft_conditions")
        ],
    )
    return None
