"""聚合 + baseline diff + 渲染报告。

判官绝对分会压缩/有偏 → 最可信的是同一冻结集上两个 label 的 delta。
所以报告核心是「label_A vs label_B 的逐维差」。
"""
from __future__ import annotations

import statistics


def aggregate_label(judged: list[dict], hardflags: list[list[dict]]) -> dict:
    """把一个 condition（label）下多局聚合成 label 级。"""
    dims: dict[str, list[float]] = {}
    overalls: list[float] = []
    jflags = 0
    for j in judged:
        for dim, v in (j.get("dim_avg") or {}).items():
            dims.setdefault(dim, []).append(v)
        if j.get("overall_avg") is not None:
            overalls.append(j["overall_avg"])
        jflags += len(j.get("judge_flags") or [])
    hard = {}
    for fl in hardflags:
        for f in fl:
            hard[f["kind"]] = hard.get(f["kind"], 0) + 1
    return {
        "n_sessions": len(judged),
        "dim_avg": {d: round(statistics.mean(xs), 2) for d, xs in dims.items() if xs},
        "overall_avg": round(statistics.mean(overalls), 2) if overalls else None,
        "judge_flag_count": jflags,
        "hardcheck_counts": hard,
    }


def render(labels: dict[str, dict], rubric: str, judge_slot: str) -> str:
    names = list(labels.keys())
    out = [f"# 评测报告 · rubric={rubric} · 判官={judge_slot}", ""]
    out.append(f"对比 condition：{' vs '.join(names)}")
    out.append("")

    # 逐维对比表
    all_dims = sorted({d for L in labels.values() for d in L["dim_avg"]})
    header = "| 维度 | " + " | ".join(names) + (" | Δ |" if len(names) == 2 else " |")
    out.append(header)
    out.append("|" + "---|" * (len(names) + (2 if len(names) == 2 else 1)))
    for dim in all_dims:
        cells = [f"{labels[n]['dim_avg'].get(dim, '—')}" for n in names]
        row = f"| {dim} | " + " | ".join(cells)
        if len(names) == 2:
            a = labels[names[0]]["dim_avg"].get(dim)
            b = labels[names[1]]["dim_avg"].get(dim)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                d = round(b - a, 2)
                row += f" | {'+' if d >= 0 else ''}{d} |"
            else:
                row += " | — |"
        else:
            row += " |"
        out.append(row)
    # overall
    cells = [f"{labels[n]['overall_avg']}" for n in names]
    row = f"| **overall** | " + " | ".join(cells)
    if len(names) == 2:
        a, b = labels[names[0]]["overall_avg"], labels[names[1]]["overall_avg"]
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            d = round(b - a, 2)
            row += f" | {'+' if d >= 0 else ''}{d} |"
        else:
            row += " | — |"
    else:
        row += " |"
    out.append(row)

    out.append("")
    out.append("## 故障 / flag")
    out.append("| condition | 局数 | 判官flag | 硬检 |")
    out.append("|---|---|---|---|")
    for n in names:
        L = labels[n]
        hard = ", ".join(f"{k}×{v}" for k, v in L["hardcheck_counts"].items()) or "无"
        out.append(f"| {n} | {L['n_sessions']} | {L['judge_flag_count']} | {hard} |")

    out.append("")
    out.append("> 注：判官绝对分有压缩/偏差，**信 Δ 不信绝对值**。Δ 为正=后者比前者好。")
    return "\n".join(out)


def render_pairwise(result: dict, rubric: str, seed: int) -> str:
    la, lb = result["labels"]
    agg = result["aggregate"]
    out = [f"# A/B 相对评测 · rubric={rubric} · seed={seed}", ""]
    out.append(f"盲判对比：**{la}** vs **{lb}**（随机左右、匿名）")
    out.append("")
    out.append("## 判官面板（各判官胜率）")
    out.append(f"| 判官 | {la} | {lb} | err | {lb} 胜率 |")
    out.append("|---|---|---|---|---|")
    for judge, c in agg["per_judge"].items():
        tot = c[la] + c[lb]
        rate = f"{c[lb]}/{tot}" if tot else "—"
        out.append(f"| {judge} | {c[la]} | {c[lb]} | {c['err']} | {rate} |")
    out.append("")
    out.append("## 逐回合共识")
    out.append(f"| turn | {la} 票 | {lb} 票 | 多数 |")
    out.append("|---|---|---|---|")
    for turn in sorted(agg["per_turn"]):
        v = agg["per_turn"][turn]
        maj = lb if v[lb] > v[la] else (la if v[la] > v[lb] else "平")
        out.append(f"| {turn} | {v[la]} | {v[lb]} | {maj} |")
    out.append("")
    out.append("> A/B 随机左右匿名盲判。判官需「强 + 与被测异源」才可信（见 README）。")
    return "\n".join(out)
