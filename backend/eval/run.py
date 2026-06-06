"""评测引擎入口。对已存在的 game_session 抓痕→硬检→判分→聚合→出报告。

按 condition(label) 分组，支持 baseline 对比（如 voice 前/后）。
判游戏不在这里（P0 复用已有 session）；新跑播放由 driver 负责（后续）。

用法：
    python -m eval.run --rubric npc \
        --group "no_voice=<sid>,<sid>" \
        --group "voice=<sid>,<sid>" \
        --out eval/runs/voice_ab.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from database import async_session
from eval.capture import capture_session, world_secrets
from eval.hardchecks import run_hardchecks
from eval.judge import judge_session
from eval.judge_pairwise import judge_pairwise_session
from eval.report import aggregate_label, render, render_pairwise


def _parse_group(s: str) -> tuple[str, list[str]]:
    label, _, rest = s.partition("=")
    sids = [x.strip() for x in rest.split(",") if x.strip()]
    return label.strip(), sids


async def run(groups: list[tuple[str, list[str]]], rubric: str, judge_slot: str, out: str) -> int:
    labels: dict[str, dict] = {}
    raw_dump: dict[str, list] = {}
    async with async_session() as db:
        for label, sids in groups:
            judged: list[dict] = []
            hardflags: list[list[dict]] = []
            for sid in sids:
                cap = await capture_session(db, sid)
                secrets = await world_secrets(db, cap["world_id"]) if cap["world_id"] else {}
                hf = run_hardchecks(cap, secrets)
                print(f"  [{label}] {sid[:8]} 抓到 {len(cap['turns'])} 回合, 硬检 {len(hf)} flag, 判分中…", flush=True)
                jv = await judge_session(db, cap, rubric, judge_slot=judge_slot)
                jv["hardflags"] = hf
                print(f"      → overall={jv['overall_avg']} dims={jv['dim_avg']} (parse_fail={jv['parse_fail']})", flush=True)
                judged.append(jv)
                hardflags.append(hf)
            labels[label] = aggregate_label(judged, hardflags)
            raw_dump[label] = judged

    md = render(labels, rubric, judge_slot)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    with out_path.with_suffix(".jsonl").open("w", encoding="utf-8") as f:
        for label, js in raw_dump.items():
            f.write(json.dumps({"label": label, "judged": js}, ensure_ascii=False) + "\n")
    print("\n" + md)
    print(f"\n报告 → {out_path}  |  原始数据 → {out_path.with_suffix('.jsonl')}")
    return 0


async def run_pairwise(groups, rubric: str, judge_slots: list[str], out: str, seed: int) -> int:
    if len(groups) != 2:
        print("pairwise 需要恰好 2 个 --group（各 1 个 session）")
        return 2
    (la, sids_a), (lb, sids_b) = groups
    if not sids_a or not sids_b:
        print("每个 --group 需要 1 个 session id")
        return 2
    async with async_session() as db:
        cap_a = await capture_session(db, sids_a[0])
        cap_b = await capture_session(db, sids_b[0])
        print(f"  抓痕：{la}={sids_a[0][:8]}({len(cap_a['turns'])}回合) vs {lb}={sids_b[0][:8]}({len(cap_b['turns'])}回合)", flush=True)
        print(f"  判官 {list(judge_slots)} 盲 A/B 判分中…", flush=True)
        result = await judge_pairwise_session(
            db, cap_a, cap_b, la, lb, rubric_name=rubric, judge_slots=tuple(judge_slots), seed=seed,
        )
    md = render_pairwise(result, rubric, seed)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    out_path.with_suffix(".jsonl").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + md)
    print(f"\n报告 → {out_path}  |  原始数据 → {out_path.with_suffix('.jsonl')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rubric", default=None, help="absolute 默认 npc；pairwise 默认 npc_pairwise")
    ap.add_argument("--judge-slot", action="append", default=[], help="判官 slot（可多次，pairwise 多判官面板）")
    ap.add_argument("--group", action="append", default=[], help='label=sid1,sid2 (可多次)')
    ap.add_argument("--out", default="eval/runs/report.md")
    ap.add_argument("--pairwise", action="store_true", help="A/B 相对评测（盲，多判官胜率）")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    if not a.group:
        print("需要至少一个 --group label=sid,...")
        return 2
    groups = [_parse_group(g) for g in a.group]
    judge_slots = a.judge_slot or ["admin_generation"]
    if a.pairwise:
        return asyncio.run(run_pairwise(groups, a.rubric or "npc_pairwise", judge_slots, a.out, a.seed))
    return asyncio.run(run(groups, a.rubric or "npc", judge_slots[0], a.out))


if __name__ == "__main__":
    sys.exit(main())
