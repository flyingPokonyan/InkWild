"""Baseline 体检：跨冻结场景跑新局 → 抓痕 → judge(npc+director) → 一张体检表。

回答"现在质量到底怎样 + 最弱维度是哪个"。输出 eval/runs/baseline_<ts>.md。
用法：python -m eval.baseline [--turns 8] [--judge-slot admin_generation]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

from database import async_session
from eval.capture import capture_session, world_secrets
from eval.examples.driver import run_playthrough
from eval.hardchecks import run_hardchecks
from eval.judge import judge_session
from eval.examples.scenarios import PERSONAS, SCENARIOS

RUBRICS = [("npc", True), ("director", False)]  # (name, skip_if_no_npc)


def _fmt_dims(d: dict) -> str:
    return "  ".join(f"{k}={v}" for k, v in d.items())


async def run(turns_override: int | None, judge_slot: str) -> int:
    rows: list[dict] = []
    async with async_session() as db:
        for sc in SCENARIOS:
            print(f"\n=== {sc['id']} 跑播放中… ===", flush=True)
            try:
                drive = await run_playthrough(
                    world_id=sc["world_id"], mode=sc["mode"], script_id=sc.get("script_id"),
                    character_id=sc["character_id"], persona=PERSONAS[sc["persona"]],
                    turns=turns_override or sc["turns"],
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  ! 驱动失败: {exc}")
                rows.append({"scenario": sc["id"], "fatal": str(exc)})
                continue
            sid = drive.get("session_id")
            if not sid:
                rows.append({"scenario": sc["id"], "fatal": "no session_id", "errors": drive.get("errors")})
                continue
            cap = await capture_session(db, sid)
            secrets = await world_secrets(db, cap["world_id"]) if cap["world_id"] else {}
            hf = run_hardchecks(cap, secrets)
            print(f"  session={sid[:8]} 抓 {len(cap['turns'])} 回合, 硬检 {len(hf)} flag, 判分中…", flush=True)
            judged = {}
            for name, skip in RUBRICS:
                jv = await judge_session(db, cap, name, judge_slot=judge_slot, skip_if_no_npc=skip)
                judged[name] = jv
                print(f"    [{name}] overall={jv['overall_avg']}  {_fmt_dims(jv['dim_avg'])}", flush=True)
            ttfts = drive.get("turn_ttfts") or []
            rows.append({
                "scenario": sc["id"], "tags": sc["tags"], "session_id": sid,
                "opening_ttft": drive.get("opening_ttft"),
                "ttft_med": round(statistics.median(ttfts), 1) if ttfts else None,
                "errors": drive.get("errors", 0), "hardflags": hf,
                "judged": {k: {"overall": v["overall_avg"], "dims": v["dim_avg"],
                               "jflags": v["judge_flags"]} for k, v in judged.items()},
            })

    md = _render(rows, judge_slot)
    out = Path(f"eval/runs/baseline_{time.strftime('%Y%m%d-%H%M')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    out.with_suffix(".jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print("\n" + md)
    print(f"\n→ {out}")
    return 0


def _render(rows: list[dict], judge_slot: str) -> str:
    good = [r for r in rows if "judged" in r]
    out = [f"# Baseline 体检 · 判官={judge_slot}", "", f"场景数：{len(rows)}（成功 {len(good)}）", ""]

    for rubric in ("npc", "director"):
        dims = sorted({d for r in good for d in r["judged"].get(rubric, {}).get("dims", {})})
        if not dims:
            continue
        out.append(f"## {rubric} 镜头（逐场景 × 维度）")
        out.append("| 场景 | " + " | ".join(dims) + " | overall |")
        out.append("|" + "---|" * (len(dims) + 2))
        for r in good:
            jd = r["judged"].get(rubric, {})
            cells = [str(jd.get("dims", {}).get(d, "—")) for d in dims]
            out.append(f"| {r['scenario']} | " + " | ".join(cells) + f" | {jd.get('overall', '—')} |")
        # 跨场景每维均值 → 找最弱维度
        col_avg = {}
        for d in dims:
            xs = [r["judged"][rubric]["dims"][d] for r in good if d in r["judged"].get(rubric, {}).get("dims", {})]
            if xs:
                col_avg[d] = round(statistics.mean(xs), 2)
        out.append(f"| **均值** | " + " | ".join(str(col_avg.get(d, "—")) for d in dims) + " | |")
        if col_avg:
            worst = min(col_avg, key=col_avg.get)
            out.append("")
            out.append(f"→ **{rubric} 最弱维度：`{worst}`（{col_avg[worst]}）** ← 下一步该攻这里")
        out.append("")

    out.append("## 客观指标 + 故障")
    out.append("| 场景 | 开场TTFT | 回合TTFT中位 | 错误 | 硬检flag | 判官flag |")
    out.append("|---|---|---|---|---|---|")
    for r in rows:
        if "fatal" in r:
            out.append(f"| {r['scenario']} | — | — | FATAL: {r['fatal']} | | |")
            continue
        hard = ", ".join(f"{f['kind']}@{f['turn']}" for f in r["hardflags"]) or "无"
        jflags = sum(len(v["jflags"]) for v in r["judged"].values())
        out.append(f"| {r['scenario']} | {r.get('opening_ttft')} | {r.get('ttft_med')} | {r.get('errors')} | {hard} | {jflags} |")

    out.append("")
    out.append("> 判官绝对分有压缩偏差：跨场景/跨维度的**相对排序 + flag** 比绝对值可信。最弱维度=优先攻。")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=None)
    ap.add_argument("--judge-slot", default="admin_generation")
    a = ap.parse_args()
    return asyncio.run(run(a.turns, a.judge_slot))


if __name__ == "__main__":
    sys.exit(main())
