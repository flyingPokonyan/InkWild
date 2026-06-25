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


# 软评门控阈值（P0「两个数」之一）：ip_consistency / collision 任一 ≤ 此值 = 设定硬伤
# （矛盾/撞车/跨时代）。软裁判是唯一能看穿这类问题的信号（硬指标只数数量）。这里**不再**
# 把它压进 overall（旧 cap-to-55 是补丁，丢信息），而是单出 blocking_flags + shippable，
# overall 保持诚实硬分进趋势，红旗在 admin 旁路显示。tension 偏主观（"平淡"≠"错"），不门控。
BLOCKING_SOFT_THRESHOLD = 4


def compute_blocking_flags(soft: dict | None) -> tuple[list[str], bool]:
    """从软裁判分算「阻断红旗」+ shippable 布尔（P0 两数门控，替代旧 cap-to-55）。

    返回 (blocking_flags, shippable)。flags 非空 = 有设定硬伤、不建议直接发布（但**只建议、
    不硬卡**，admin 仍可发）。soft 缺失/未跑 → 无法判定，按"暂不阻断"(shippable=True) 处理。
    """
    if not soft:
        return [], True
    flags: list[str] = []
    for key in ("ip_consistency", "collision"):
        v = soft.get(key)
        if isinstance(v, int) and v <= BLOCKING_SOFT_THRESHOLD:
            flags.append(f"{key}={v}")
    return flags, not flags


def compute_hard_metrics(payload: dict, ip_must_have: list[str] | None = None) -> dict:
    """诚实硬指标 + 安全网 + overall_score(0-100,仅硬指标,软分不参与)。

    P0 三处改动让分变诚实（不再"靠兜底撑满"）：
    - must_have 覆盖按 **真实覆盖**算（扣掉 backfill 补回的）：靠安全网救回来的不算数，
      否则 must_have 40 分被 backfill 撑成恒满，分永远看不出问题（十日终焉式 99 分根因）。
    - structure 分母从 char×3 收紧到 char×1.5：P2 地点对账消灭了海量 schedule 悬空 warning 后，
      剩下的 warning 更该被如实计入。
    - prune 扣分：strict 删掉的非原作角色越多 = 规划越跑偏，按量扣（封顶 20）。
    """
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
    # 随角色规模缩放，但分母收紧到 char×1.5（旧 char×3 太宽容、海量 warning 也压不低分）。
    structure_score = max(0.0, 1.0 - len(shape_warnings) / max(1.0, character_count * 1.5))

    safety = _safety_net(payload)
    backfill_count = safety["backfill_count"]
    prune_count = safety["prune_count"]

    # must_have 真实覆盖 = 最终覆盖 − backfill 补回的（靠兜底救回来的不计入诚实分）。
    genuine_covered = max(0, must_have_covered - backfill_count)
    mh_ratio = (genuine_covered / must_have_total) if must_have_total else 1.0
    char_ratio = min(1.0, character_count / 12.0)
    play_ratio = min(1.0, playable_count / 8.0)
    base = 40 * mh_ratio + 20 * char_ratio + 20 * play_ratio + 20 * structure_score
    # prune 扣分：每个被裁掉的 AI 杜撰角色 −4，封顶 −20。
    prune_penalty = min(20.0, prune_count * 4.0)
    overall = round(max(0.0, base - prune_penalty), 1)

    return {
        "character_count": character_count,
        "playable_count": playable_count,
        "must_have_total": must_have_total,
        "must_have_covered": must_have_covered,
        "must_have_genuine_covered": genuine_covered,
        "events_count": events_count,
        "shared_events_count": shared_events_count,
        "structure_score": round(structure_score, 3),
        "shape_warnings": shape_warnings,
        "backfill_count": backfill_count,
        "prune_count": prune_count,
        "prune_penalty": round(prune_penalty, 1),
        "soft_warning_count": safety["soft_warning_count"],
        "safety_net": safety,
        "overall_score": overall,
    }
