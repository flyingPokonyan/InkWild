"""生成质量 — Python 硬指标 + 安全网触发量(0 成本,可纵向趋势对比)。

plan: docs/plans/2026-06-24-generation-agentic-loop.md §4.2 / §5
纯函数:吃最终 payload(+ ip_must_have 名单),吐结构化指标。不调 LLM、不碰 DB。
软分(LLM)在 world_quality_scorer 里另算,不在这。
"""
from __future__ import annotations

import re

from services.world_critic_service import validate_world_shape


def _norm_name(name: str) -> str:
    return re.sub(r"[\s·•・]", "", str(name or "")).strip()


def _character_names(payload: dict) -> list[str]:
    chars = payload.get("world_characters") or []
    return [str(c.get("name", "")) for c in chars if isinstance(c, dict)]


def _playable_count(payload: dict) -> int:
    # 优先 world_characters 里 playable=True;退回独立 playable 列表长度。
    chars = payload.get("world_characters") or []
    pc = sum(1 for c in chars if isinstance(c, dict) and c.get("playable"))
    if pc:
        return pc
    pl = payload.get("playable") or []
    return len(pl) if isinstance(pl, list) else 0


def _safety_net(payload: dict) -> dict:
    """从 quality_warnings 解析安全网触发量。

    backfill: critic 阶段补回 must_have(code=must_have_backfilled),一条 warning 列多个名字。
    prune:    roster 删非 canon —— 当前只 structlog、未进 quality_warnings,MVP 取不到记 0
              (plan §10:后续要补埋点)。
    """
    warnings = payload.get("quality_warnings") or []
    if not isinstance(warnings, list):
        warnings = []

    backfill_names: list[str] = []
    prune_count = 0
    for w in warnings:
        if not isinstance(w, dict):
            continue
        code = str(w.get("code") or (w.get("payload") or {}).get("code") or "")
        msg = str(w.get("message") or (w.get("payload") or {}).get("message") or "")
        if code == "must_have_backfilled":
            # message 形如「必含角色 A, B 在详情阶段丢失，已用原作数据补回...」
            m = re.search(r"必含角色\s*([^在]+?)\s*在详情", msg)
            if m:
                backfill_names = [n.strip() for n in re.split(r"[,，、]", m.group(1)) if n.strip()]
            else:
                backfill_names.append(msg[:40])
        elif code == "roster_pruned_non_canon":
            # message 形如「strict 复刻删掉了 N 个非原作角色…」
            m = re.search(r"删掉了\s*(\d+)\s*个", msg)
            prune_count = int(m.group(1)) if m else prune_count

    return {
        "backfill_count": len(backfill_names),
        "backfill_names": backfill_names,
        "prune_count": prune_count,
        "prune_available": True,
        "soft_warning_count": len(warnings),
    }


def compute_hard_metrics(payload: dict, ip_must_have: list[str] | None = None) -> dict:
    """硬指标 + 安全网 + overall_score(0-100,仅硬指标加权,软分不参与)。"""
    names = _character_names(payload)
    norm_names = {_norm_name(n) for n in names if n}
    character_count = len(names)
    playable_count = _playable_count(payload)

    must_have = [n for n in (ip_must_have or []) if n]
    must_have_total = len(must_have)
    must_have_covered = sum(1 for n in must_have if _norm_name(n) in norm_names)

    events = payload.get("events_data") or []
    shared_events = payload.get("shared_events") or []
    events_count = len(events) if isinstance(events, list) else 0
    shared_events_count = len(shared_events) if isinstance(shared_events, list) else 0

    try:
        shape_warnings = validate_world_shape(payload) or []
    except Exception:  # noqa: BLE001
        shape_warnings = []
    # 随角色规模缩放：shape_warnings 多为轻微项(如 schedule 引用未知 location)，
    # 不能线性归零——实测好世界(紫禁深宫 24w / 灰雾迷城 9w)warning 数本就随角色数涨。
    # 分母用 character_count*3，让"好世界少量 warning"仍得高分、只有海量 warning 才压低。
    structure_score = max(0.0, 1.0 - len(shape_warnings) / max(1.0, character_count * 3.0))

    safety = _safety_net(payload)

    # overall: must_have 覆盖 40 / 角色数 20 / 可玩数 20 / 结构 20
    mh_ratio = (must_have_covered / must_have_total) if must_have_total else 1.0
    char_ratio = min(1.0, character_count / 12.0)
    play_ratio = min(1.0, playable_count / 8.0)
    overall = round(40 * mh_ratio + 20 * char_ratio + 20 * play_ratio + 20 * structure_score, 1)

    return {
        "character_count": character_count,
        "playable_count": playable_count,
        "must_have_total": must_have_total,
        "must_have_covered": must_have_covered,
        "events_count": events_count,
        "shared_events_count": shared_events_count,
        "structure_score": round(structure_score, 3),
        "shape_warnings": shape_warnings,
        "backfill_count": safety["backfill_count"],
        "prune_count": safety["prune_count"],
        "soft_warning_count": safety["soft_warning_count"],
        "safety_net": safety,
        "overall_score": overall,
    }
