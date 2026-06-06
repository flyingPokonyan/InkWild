"""LLM-as-judge：拿一张 rubric（镜头）逐回合给 NPC 台词打分，再聚合。

判官模型必须强于被测（默认走 admin_generation 槽 = v4-pro，reasoning 开，判得更细）。
map-reduce：逐回合判（map）→ 均值聚合（reduce）。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from services.model_management import resolve_slot_router

RUBRIC_DIR = Path(__file__).parent / "rubrics"


def load_rubric(name: str) -> str:
    return (RUBRIC_DIR / f"{name}.md").read_text(encoding="utf-8")


def loads_lenient(text: str) -> dict | None:
    """容错解析判官输出：跨家族模型常给前缀垃圾（kimi 的 `>`）、markdown 代码块、或 JSON
    后跟解释文字。剥 ``` 围栏 → 从第一个 `{` 用 raw_decode 取第一个 JSON 对象（忽略尾随文本）。
    严格 ``json.loads`` 对这些会静默 parse_fail，导致跨家族判官全废（见 README 已知坑）。"""
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith("```"):
        s = s.strip("`")
        if s[:4].lower() == "json":
            s = s[4:]
        s = s.strip()
    i = s.find("{")
    if i < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(s[i:])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _state_block(turn: dict, prev_snap: dict) -> str:
    """导演镜头需要的"效果"：当前幕 / 本回合发言人 / 新线索 / 新事件（vs 上回合 delta）。"""
    snap = turn.get("state_snapshot") or {}
    npc = turn.get("npc_dialogues") or {}
    disc = snap.get("discovered_clues") or []
    new_clues = [c for c in disc if c not in (prev_snap.get("discovered_clues") or [])]
    trig = snap.get("triggered_events") or []
    new_events = [e for e in trig if e not in (prev_snap.get("triggered_events") or [])]
    lines = [
        f"- 当前幕(narrative_arc)：{snap.get('narrative_arc')}　高潮轮数：{snap.get('rounds_in_climax')}",
        f"- 本回合发言 NPC：{', '.join(npc.keys()) or '无'}",
        f"- 本回合新发现线索：{new_clues or '无'}",
        f"- 本回合新触发事件：{new_events or '无'}",
    ]
    return "\n".join(lines)


def _build_turn_user(turn: dict, prev_snap: dict) -> str:
    npc = turn.get("npc_dialogues") or {}
    npc_block = "\n".join(f"- {k}：{v}" for k, v in npc.items()) or "（本回合无 NPC 台词）"
    return (
        f"【玩家这步动作】{turn.get('player_action') or '（开场）'}\n\n"
        f"【旁白成品（截断）】{(turn.get('narrative') or '')[:600]}\n\n"
        f"【本回合逐 NPC 台词】\n{npc_block}\n\n"
        f"【本回合状态/效果】\n{_state_block(turn, prev_snap)}\n\n"
        f"请按 rubric 给本回合打分，只输出 JSON。"
    )


async def _judge_one_turn(router, rubric_text: str, turn: dict, prev_snap: dict) -> dict | None:
    parts: list[str] = []
    async for ev in router.stream_json(
        messages=[{"role": "user", "content": _build_turn_user(turn, prev_snap)}],
        system=rubric_text,
        max_tokens=1200,
    ):
        if ev.get("type") == "text_delta":
            parts.append(ev.get("text", ""))
    return loads_lenient("".join(parts))


async def judge_session(db, captured: dict, rubric_name: str, *, judge_slot: str = "admin_generation",
                        skip_if_no_npc: bool = True) -> dict:
    rubric_text = load_rubric(rubric_name)
    router = await resolve_slot_router(db, judge_slot)
    if router is None:
        raise RuntimeError(f"no judge router for slot {judge_slot}")

    per_turn: list[dict] = []
    prev_snap: dict = {}
    for turn in captured.get("turns", []):
        if skip_if_no_npc and not (turn.get("npc_dialogues") or {}):
            prev_snap = turn.get("state_snapshot") or prev_snap
            continue
        verdict = await _judge_one_turn(router, rubric_text, turn, prev_snap)
        per_turn.append({"turn": turn["turn"], "verdict": verdict})
        prev_snap = turn.get("state_snapshot") or prev_snap

    # reduce：逐维均值 + overall 均值 + flags 汇总
    dim_scores: dict[str, list[float]] = {}
    overalls: list[float] = []
    all_flags: list[dict] = []
    parse_fail = 0
    for pt in per_turn:
        v = pt["verdict"]
        if not isinstance(v, dict):
            parse_fail += 1
            continue
        for dim, d in (v.get("per_dim") or {}).items():
            try:
                dim_scores.setdefault(dim, []).append(float(d.get("score")))
            except (TypeError, ValueError, AttributeError):
                pass
        try:
            overalls.append(float(v.get("overall")))
        except (TypeError, ValueError):
            pass
        for f in (v.get("flags") or []):
            all_flags.append({"turn": pt["turn"], "flag": f})

    dim_avg = {dim: round(statistics.mean(xs), 2) for dim, xs in dim_scores.items() if xs}
    return {
        "session_id": captured["session_id"],
        "rubric": rubric_name,
        "judge_slot": judge_slot,
        "n_judged_turns": len(per_turn),
        "parse_fail": parse_fail,
        "dim_avg": dim_avg,
        "overall_avg": round(statistics.mean(overalls), 2) if overalls else None,
        "judge_flags": all_flags,
        "per_turn": per_turn,
    }
