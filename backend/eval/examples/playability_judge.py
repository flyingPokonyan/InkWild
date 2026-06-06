"""一次性「判」：对 playability_campaign 跑出的局做多镜头 + 多判官体检 + 进展度量。

每个 session：capture → hardchecks → 用 3 个跨家族判官（qwen3.7-max / glm-5.1 / kimi-k2.6）
绝对判 [npc, director, ip_fidelity]（并行 + 采样）→ 共识均分 + 各判官分开列 + flag 汇总；
另算剧情进展（幕推进 / 线索增长 / 事件 / 是否到结局）。
判官走 env：XFAM_BASE / XFAM_KEY（devops 网关，跨家族 + 中文懂甄嬛传）。
跑：
    docker exec -e XFAM_BASE=.. -e XFAM_KEY=.. talealive-backend-1 \
      python -m eval.examples.playability_judge eval/runs/playability_<ts>
产物：<dir>/report.md + <dir>/judged.jsonl
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import sys

from database import async_session
from eval.capture import capture_session, world_secrets
from eval.hardchecks import run_hardchecks
from eval.judge import _judge_one_turn, load_rubric
from llm.openai_compatible import OpenAICompatibleProvider
from llm.router import LLMRouter

BASE = os.environ["XFAM_BASE"]
KEY = os.environ["XFAM_KEY"]
JUDGES = [m.strip() for m in os.environ.get(
    "XFAM_JUDGES", "dashscope/qwen3.7-max,dashscope/glm-5.1,dashscope/kimi-k2.6").split(",") if m.strip()]
SEM = asyncio.Semaphore(int(os.environ.get("XFAM_JUDGE_CONCURRENCY", "3")))
# 采样：每 N 回合判一次（首2回合必判）。控住 3 判官的成本/时间。
SAMPLE = {"npc": 2, "director": 2, "ip_fidelity": 3}
NEED_NPC = {"npc": True, "director": False, "ip_fidelity": False}


def _short(m: str) -> str:
    return m.split("/")[-1]


def _router(model: str) -> LLMRouter:
    p = OpenAICompatibleProvider(api_key=KEY, base_url=BASE, model=model)
    return LLMRouter(providers={model: p}, fallback_chain=[model],
                     identity={"model_id": model}, reasoning=False)


def _reduce(per_turn: list[tuple[int, dict | None]]) -> dict:
    dim: dict[str, list[float]] = {}
    overalls: list[float] = []
    flags: list[dict] = []
    parse_fail = 0
    for tn, v in per_turn:
        if not isinstance(v, dict):
            parse_fail += 1
            continue
        for k, d in (v.get("per_dim") or {}).items():
            try:
                dim.setdefault(k, []).append(float(d.get("score")))
            except (TypeError, ValueError, AttributeError):
                pass
        try:
            overalls.append(float(v.get("overall")))
        except (TypeError, ValueError):
            pass
        for f in (v.get("flags") or []):
            flags.append({"turn": tn, "flag": f})
    return {
        "dim_avg": {k: round(statistics.mean(xs), 2) for k, xs in dim.items() if xs},
        "overall": round(statistics.mean(overalls), 2) if overalls else None,
        "flags": flags, "parse_fail": parse_fail, "n_judged": len(per_turn),
    }


async def _judge_turn(router, rubric_text, turn, prev_snap):
    """单回合判分，带退避重试 + 异常吞没（防 burst 限流 / 单点失败拖垮整盘）。"""
    for attempt in range(5):
        try:
            async with SEM:
                v = await _judge_one_turn(router, rubric_text, turn, prev_snap)
            return (turn["turn"], v)
        except Exception as e:  # noqa: BLE001
            if attempt == 4:
                return (turn["turn"], None)
            # burst/限流退避，其它错也退避重试一次
            await asyncio.sleep(1.5 * (2 ** attempt) + random.random())
    return (turn["turn"], None)


async def _judge_rubric(router, rubric_text, turns, *, need_npc=False, sample_every=1) -> dict:
    tasks, prev = [], {}
    for i, t in enumerate(turns):
        snap = t.get("state_snapshot") or {}
        if need_npc and not (t.get("npc_dialogues") or {}):
            prev = snap or prev
            continue
        if sample_every > 1 and i >= 2 and i % sample_every != 0:
            prev = snap or prev
            continue
        tasks.append(_judge_turn(router, rubric_text, t, dict(prev)))
        prev = snap or prev
    results = await asyncio.gather(*tasks) if tasks else []
    return _reduce(results)


def _progression(cap: dict) -> dict:
    turns = cap.get("turns", [])
    snaps = [(t["turn"], t.get("state_snapshot") or {}) for t in turns]
    acts = [(s.get("narrative_arc") or {}).get("current_act") for _, s in snaps]
    clue_counts = [len(s.get("discovered_clues") or []) for _, s in snaps]
    ev_counts = [len(s.get("triggered_events") or []) for _, s in snaps]
    final = snaps[-1][1] if snaps else {}
    arc = final.get("narrative_arc") or {}
    ending = bool(final.get("ending_triggered") or final.get("ending") or arc.get("ending_triggered"))
    prog = sum(1 for i in range(1, len(turns))
               if clue_counts[i] > clue_counts[i - 1] or ev_counts[i] > ev_counts[i - 1])
    return {
        "n_turns": len(turns),
        "acts_seen": sorted({a for a in acts if a}),
        "final_act": arc.get("current_act"),
        "reached_climax": any(a == "climax" for a in acts),
        "max_clues": max(clue_counts) if clue_counts else 0,
        "final_events": ev_counts[-1] if ev_counts else 0,
        "ending_reached": ending,
        "progress_turns": prog,
        "rounds_in_climax": final.get("rounds_in_climax"),
    }


def _consensus(per_judge: dict[str, dict]) -> dict:
    overalls = [r["overall"] for r in per_judge.values() if r["overall"] is not None]
    dims: dict[str, list[float]] = {}
    for r in per_judge.values():
        for k, v in r["dim_avg"].items():
            dims.setdefault(k, []).append(v)
    all_flags = []
    for jn, r in per_judge.items():
        for f in r["flags"]:
            all_flags.append({"judge": jn, **f})
    return {
        "consensus_overall": round(statistics.mean(overalls), 2) if overalls else None,
        "dim_consensus": {k: round(statistics.mean(xs), 2) for k, xs in dims.items() if xs},
        "per_judge": {jn: {"overall": r["overall"], "dim_avg": r["dim_avg"],
                           "parse_fail": r["parse_fail"], "n": r["n_judged"]} for jn, r in per_judge.items()},
        "all_flags": all_flags,
    }


async def judge_one(ms: dict) -> dict:
    sid = ms.get("session_id")
    out = {**{k: ms.get(k) for k in ("id", "mode", "persona", "tags", "errors",
                                     "opening_ttft", "ttft_med")}, "session_id": sid}
    if not sid:
        out["status"] = "no_session"
        return out
    async with async_session() as db:
        cap = await capture_session(db, sid)
        secrets = await world_secrets(db, cap.get("world_id") or ms.get("world_id", ""))
    routers = {_short(m): _router(m) for m in JUDGES}
    rubrics = {ln: load_rubric(ln) for ln in SAMPLE}
    keys = [(ln, jn) for ln in rubrics for jn in routers]
    results = await asyncio.gather(*[
        _judge_rubric(routers[jn], rubrics[ln], cap["turns"],
                      need_npc=NEED_NPC[ln], sample_every=SAMPLE[ln])
        for (ln, jn) in keys
    ])
    res_map = dict(zip(keys, results))
    lenses = {ln: _consensus({jn: res_map[(ln, jn)] for jn in routers}) for ln in rubrics}
    out.update({
        "hardflags": run_hardchecks(cap, secrets),
        "lenses": lenses,
        "progression": _progression(cap),
        "status": "ok",
    })
    p = out["progression"]
    print(f"[judged] {out['id']} npc={lenses['npc']['consensus_overall']} "
          f"dir={lenses['director']['consensus_overall']} ip={lenses['ip_fidelity']['consensus_overall']} "
          f"hard={len(out['hardflags'])} prog={p['progress_turns']}/{p['n_turns']} "
          f"act={p['final_act']} end={p['ending_reached']}", flush=True)
    return out


def _render(judged: list[dict]) -> str:
    L = [f"# 可玩性体检报告 · {len(JUDGES)}判官面板（{', '.join(_short(m) for m in JUDGES)}）", ""]
    L.append("## 总览（逐局，分=3判官共识）")
    L.append("| 局 | 模式 | persona | 回合 | err | TTFT中位 | NPC | 导演 | IP | 硬检 | 进展 | 终幕 | 结局 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for j in judged:
        if j.get("status") != "ok":
            L.append(f"| {j.get('id')} | {j.get('mode')} | {j.get('persona')} | — | {j.get('errors')} "
                     f"| — | — | — | — | — | — | — | {j.get('status')} |")
            continue
        p, ln = j["progression"], j["lenses"]
        L.append(f"| {j['id']} | {j['mode']} | {j['persona']} | {p['n_turns']} | {j.get('errors')} "
                 f"| {j.get('ttft_med')} | {ln['npc']['consensus_overall']} "
                 f"| {ln['director']['consensus_overall']} | {ln['ip_fidelity']['consensus_overall']} "
                 f"| {len(j['hardflags'])} | {p['progress_turns']}/{p['n_turns']} "
                 f"| {p['final_act']} | {'✅' if p['ending_reached'] else '✗'} |")
    oks = [j for j in judged if j.get("status") == "ok"]
    # 维度共识均值
    for lens in ("npc", "director", "ip_fidelity"):
        dims: dict[str, list[float]] = {}
        for j in oks:
            for k, v in j["lenses"][lens]["dim_consensus"].items():
                dims.setdefault(k, []).append(v)
        if dims:
            L += ["", f"## {lens} 维度均值（跨局·判官共识）", "| 维度 | 均值 | 最低局 |", "|---|---|---|"]
            for k, xs in dims.items():
                lo = min(oks, key=lambda j: j["lenses"][lens]["dim_consensus"].get(k, 9))
                L.append(f"| {k} | {round(statistics.mean(xs), 2)} | {lo['id']}={lo['lenses'][lens]['dim_consensus'].get(k)} |")
    # 判官间分歧（每局每镜头 per-judge overall）
    L += ["", "## 判官间一致性（per-judge overall，看分歧）"]
    L.append("| 局 | 镜头 | " + " | ".join(_short(m) for m in JUDGES) + " |")
    L.append("|---|---|" + "---|" * len(JUDGES))
    for j in oks:
        for lens in ("npc", "director", "ip_fidelity"):
            pj = j["lenses"][lens]["per_judge"]
            row = " | ".join(str(pj.get(_short(m), {}).get("overall")) for m in JUDGES)
            L.append(f"| {j['id']} | {lens} | {row} |")
    # flag 汇总
    L += ["", "## 判官 flag + 硬检 flag 汇总"]
    for j in oks:
        jf = [f"{f['judge']}@t{f['turn']}:{f['flag']}" for lens in ("npc", "director", "ip_fidelity")
              for f in j["lenses"][lens]["all_flags"]]
        hf = [(h["turn"], h["kind"]) for h in j["hardflags"]]
        if jf or hf:
            L.append(f"- **{j['id']}**：判官 {jf if jf else '无'}；硬检 {hf if hf else '无'}")
    return "\n".join(L)


async def main(run_dir: str) -> None:
    manifest = json.load(open(os.path.join(run_dir, "manifest.json")))
    judged = [await judge_one(s) for s in manifest["sessions"]]
    with open(os.path.join(run_dir, "judged.jsonl"), "w") as f:
        for j in judged:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")
    md = _render(judged)
    with open(os.path.join(run_dir, "report.md"), "w") as f:
        f.write(md)
    print("\n" + md)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
