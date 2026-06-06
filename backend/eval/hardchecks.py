"""规则故障检测（确定性，独立于判官打分）。

输入：capture_session 的结果 + world_secrets。输出：flag 列表。
这些是便宜的"硬红旗"——细腻语义版交判官。
"""
from __future__ import annotations

_META_MARKERS = ("剧情", "作品", "演员", "观众", "第四面墙", "剧里", "书里", "原著", "小说里", "你是NPC", "你是 NPC")


def _char_overlap(a: str, b: str) -> float:
    """粗暴近重复度：较短串里有多大比例的 3-gram 出现在较长串里。"""
    if not a or not b:
        return 0.0
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    grams = {short[i:i + 3] for i in range(max(0, len(short) - 2))}
    if not grams:
        return 0.0
    hit = sum(1 for g in grams if g in long)
    return hit / len(grams)


def run_hardchecks(captured: dict, secrets: dict[str, str]) -> list[dict]:
    flags: list[dict] = []
    turns = captured.get("turns", [])

    for t in turns:
        tn = t["turn"]
        npc = t.get("npc_dialogues") or {}
        snap = t.get("state_snapshot") or {}
        discovered = " ".join(str(x) for x in (snap.get("discovered_clues") or []))
        discovered += " " + " ".join(str(x) for x in (snap.get("info_items") or []))

        # 空回合（无旁白 = 该回合废了）
        if not (t.get("narrative") or "").strip() and not npc:
            flags.append({"turn": tn, "kind": "empty_turn", "detail": "无旁白且无NPC台词"})

        for name, line in npc.items():
            line = str(line or "")
            # 破第四面墙（规则预筛）
            for mk in _META_MARKERS:
                if mk in line:
                    flags.append({"turn": tn, "kind": "meta_marker", "detail": f"{name}台词含「{mk}」"})
                    break
            # 秘密泄漏粗筛：自己的秘密文本出现在台词里，且尚未被发现
            sec = secrets.get(name)
            if sec and len(sec) >= 6:
                if _char_overlap(sec, line) >= 0.5 and _char_overlap(sec, discovered) < 0.5:
                    flags.append({"turn": tn, "kind": "secret_leak", "detail": f"{name}疑似抖出自己秘密"})

    # 旁白近重复：对最近 3 条「非空」旁白比，隔回合复读也能抓（空回合不打断窗口）
    prev_narrs: list[tuple[int, str]] = []
    for t in turns:
        narr = (t.get("narrative") or "").strip()
        if not narr:
            continue
        for ptn, pnarr in prev_narrs[-3:]:
            ov = _char_overlap(pnarr, narr)
            if ov >= 0.6:
                flags.append({"turn": t["turn"], "kind": "repetition", "detail": f"与第{ptn}回合旁白近重复({ov:.0%})"})
                break
        prev_narrs.append((t["turn"], narr))

    return flags
