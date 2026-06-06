"""Pairwise（A/B 相对评测）镜头：对两个 condition 的同回合 NPC 台词做盲 A/B 比较。

为什么 pairwise：绝对单回合打分会饱和压缩（见 README 校准 TODO + npc.md）。A/B 相对比较
在「强、且与被测异源」的判官之间稳健可复现（已用 Claude+Qwen+GLM+Kimi 4 家族验证）。

- build_pairs：回合对齐（只取两边都有 NPC 台词的共同 turn）+ 盲随机左右（seed 固定可复现）
- aggregate_pairwise：多判官胜率 + 逐回合共识
判官的 LLM 调用在 run 层（这里只放确定性逻辑，便于单测）。
"""
from __future__ import annotations

import json
import random
import re


def parse_pairwise_verdict(text: str, pair: dict) -> dict:
    """判官输出 → {turn, pick, winner_label, reason}；映射用 pair 的盲 label。解析不出则 error。"""
    obj = None
    m = re.findall(r'\{[^{}]*"winner"[^{}]*\}', text or "", re.S)
    if m:
        try:
            obj = json.loads(m[-1])
        except json.JSONDecodeError:
            obj = None
    w = str(obj.get("winner", "")).strip().upper() if isinstance(obj, dict) else ""
    reason = (obj.get("reason") or "") if isinstance(obj, dict) else ""
    if w not in ("A", "B"):
        m2 = re.search(r'winner["\s:：]+["\']?([AB])', text or "", re.I)
        w = m2.group(1).upper() if m2 else ""
    if w not in ("A", "B"):
        return {"turn": pair["turn"], "error": "parse_fail", "raw": (text or "").strip()[:160]}
    winner_label = pair["A_label"] if w == "A" else pair["B_label"]
    return {"turn": pair["turn"], "pick": w, "winner_label": winner_label, "reason": reason}


def build_pairs(cap_a: dict, cap_b: dict, label_a: str, label_b: str, seed: int = 42) -> list[dict]:
    """两个 captured 按共同 turn 对齐成 A/B 对；随机左右并藏 label（盲）。"""
    a_by_turn = {t["turn"]: t for t in cap_a.get("turns", []) if t.get("npc_dialogues")}
    b_by_turn = {t["turn"]: t for t in cap_b.get("turns", []) if t.get("npc_dialogues")}
    common = sorted(set(a_by_turn) & set(b_by_turn))
    src = {label_a: a_by_turn, label_b: b_by_turn}
    rnd = random.Random(seed)
    pairs: list[dict] = []
    for tn in common:
        flip = rnd.random() < 0.5
        a_label, b_label = (label_b, label_a) if flip else (label_a, label_b)
        pairs.append({
            "turn": tn,
            "A_label": a_label,
            "B_label": b_label,
            "player_action": a_by_turn[tn].get("player_action"),
            "A": src[a_label][tn].get("npc_dialogues") or {},
            "B": src[b_label][tn].get("npc_dialogues") or {},
        })
    return pairs


def _fmt_npc(d: dict) -> str:
    return "\n".join(f"- {k}：{v}" for k, v in (d or {}).items()) or "（无 NPC 台词）"


def _build_pair_user(pair: dict) -> str:
    return (
        f"【玩家动作（两版相同）】{pair.get('player_action') or '（开场，玩家尚未行动）'}\n\n"
        f"【版本 A · 在场 NPC 台词】\n{_fmt_npc(pair['A'])}\n\n"
        f"【版本 B · 在场 NPC 台词】\n{_fmt_npc(pair['B'])}\n\n"
        f"哪个版本 NPC 整体更好？只输出 JSON。"
    )


async def _ask_pair(router, rubric_text: str, pair: dict) -> str:
    parts: list[str] = []
    async for ev in router.stream_json(
        messages=[{"role": "user", "content": _build_pair_user(pair)}],
        system=rubric_text,
        max_tokens=600,
    ):
        if ev.get("type") == "text_delta":
            parts.append(ev.get("text", ""))
    return "".join(parts)


async def judge_pairwise_session(
    db, cap_a: dict, cap_b: dict, label_a: str, label_b: str, *,
    rubric_name: str = "npc_pairwise",
    judge_slots: tuple[str, ...] = ("admin_generation",),
    seed: int = 42,
) -> dict:
    """对两个 captured 做盲 A/B：每个判官 slot 逐对判，聚合多判官胜率。"""
    from eval.judge import load_rubric
    from services.model_management import resolve_slot_router

    rubric_text = load_rubric(rubric_name)
    pairs = build_pairs(cap_a, cap_b, label_a, label_b, seed=seed)
    judge_results: dict[str, list[dict]] = {}
    for slot in judge_slots:
        router = await resolve_slot_router(db, slot)
        if router is None:
            raise RuntimeError(f"no judge router for slot {slot}")
        results: list[dict] = []
        for p in pairs:
            text = await _ask_pair(router, rubric_text, p)
            results.append(parse_pairwise_verdict(text, p))
        judge_results[slot] = results
    return {
        "labels": [label_a, label_b],
        "pairs": [{"turn": p["turn"], "A_label": p["A_label"], "B_label": p["B_label"]} for p in pairs],
        "judge_results": judge_results,
        "aggregate": aggregate_pairwise(judge_results, (label_a, label_b)),
    }


def aggregate_pairwise(judge_results: dict[str, list[dict]], labels: tuple[str, str]) -> dict:
    """judge_results: {judge_name: [{turn, winner_label} | {turn, error}]} → 胜率 + 逐回合共识。"""
    la, lb = labels
    per_judge: dict[str, dict] = {}
    per_turn: dict[int, dict] = {}
    for judge, results in judge_results.items():
        counts = {la: 0, lb: 0, "err": 0}
        for r in results:
            wl = r.get("winner_label")
            if "error" in r or wl not in (la, lb):
                counts["err"] += 1
                continue
            counts[wl] += 1
            slot = per_turn.setdefault(r["turn"], {la: 0, lb: 0})
            slot[wl] += 1
        per_judge[judge] = counts
    return {"per_judge": per_judge, "per_turn": per_turn}
