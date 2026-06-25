"""generation_rubric 纯函数测试 —— 诚实硬分 + 两数门控（替代旧 cap-to-55）。"""
from services.generation_rubric import (
    BLOCKING_SOFT_THRESHOLD,
    compute_blocking_flags,
    compute_hard_metrics,
)


# ---- 两数门控（blocking_flags / shippable）----

def test_blocking_flags_on_ip_contradiction():
    # 十日终焉式：设定撕裂(ip=4 col=3)→ 红旗 + 不可发布；但 overall 不再被压扁。
    flags, shippable = compute_blocking_flags({"ip_consistency": 4, "collision": 3, "tension": 5})
    assert "ip_consistency=4" in flags and "collision=3" in flags
    assert shippable is False


def test_blocking_flags_on_one_dim_only():
    # 如鸢式：ip 触底但 collision 还行 → 仍红旗，只记触底项。
    flags, shippable = compute_blocking_flags({"ip_consistency": 4, "collision": 7, "tension": 9})
    assert flags == ["ip_consistency=4"]
    assert shippable is False


def test_blocking_flags_healthy_world():
    flags, shippable = compute_blocking_flags({"ip_consistency": 10, "collision": 9, "tension": 9})
    assert flags == []
    assert shippable is True


def test_blocking_flags_low_tension_does_not_block():
    # tension 偏低不是"错"(平淡≠矛盾)，不门控。
    flags, shippable = compute_blocking_flags({"ip_consistency": 9, "collision": 7, "tension": 3})
    assert flags == []
    assert shippable is True


def test_blocking_flags_threshold_boundary():
    # 恰好等于阈值 → 触发；阈值+1 → 不触发。
    flags_at, _ = compute_blocking_flags({"ip_consistency": BLOCKING_SOFT_THRESHOLD, "collision": 9})
    flags_above, _ = compute_blocking_flags({"ip_consistency": BLOCKING_SOFT_THRESHOLD + 1, "collision": 9})
    assert flags_at and not flags_above


def test_blocking_flags_noop_when_soft_missing():
    # 软评未跑 → 无法判定，按"暂不阻断"。
    flags, shippable = compute_blocking_flags(None)
    assert flags == []
    assert shippable is True


# ---- 诚实硬分 ----

def _payload(n_chars: int, n_playable: int, warnings: list | None = None) -> dict:
    chars = [
        {"name": f"角色{i}", "playable": i < n_playable}
        for i in range(n_chars)
    ]
    return {
        "world_characters": chars,
        "events_data": [{"id": "e1"}],
        "shared_events": [],
        "quality_warnings": warnings or [],
        "locations": [],
    }


def test_hard_metrics_basic():
    hard = compute_hard_metrics(_payload(3, 2), ip_must_have=["角色0", "角色1"])
    assert hard["character_count"] == 3
    assert hard["playable_count"] == 2
    assert hard["must_have_total"] == 2
    assert hard["must_have_covered"] == 2
    assert hard["must_have_genuine_covered"] == 2
    assert 0.0 <= hard["overall_score"] <= 100.0


def test_hard_metrics_backfill_docks_must_have():
    # 甄嬛式：must_have 看似全覆盖，但有 3 个是 backfill 补回的 → 真实覆盖扣掉它们。
    warnings = [{
        "code": "must_have_backfilled",
        "message": "必含角色 皇帝, 华妃, 皇后 在详情阶段丢失，已用原作数据补回",
    }]
    must_have = ["甄嬛", "皇帝", "华妃", "皇后", "果郡王", "沈眉庄"]
    payload = _payload(12, 6, warnings)
    # 把 must_have 名字塞进角色表，模拟"最终覆盖满"。
    payload["world_characters"] = [{"name": n, "playable": True} for n in must_have] + [
        {"name": f"配角{i}"} for i in range(6)
    ]
    hard = compute_hard_metrics(payload, ip_must_have=must_have)
    assert hard["backfill_count"] == 3
    assert hard["must_have_covered"] == 6           # 最终全覆盖
    assert hard["must_have_genuine_covered"] == 3   # 真实只挣到 3 个
    # 诚实分应明显低于"假装全覆盖"的满分。
    clean = compute_hard_metrics(
        {**payload, "quality_warnings": []}, ip_must_have=must_have
    )
    assert hard["overall_score"] < clean["overall_score"]


def test_hard_metrics_prune_penalty():
    warnings = [{
        "code": "roster_pruned_non_canon",
        "message": "strict 复刻删掉了 5 个非原作角色（AI 编造、已裁剪）",
    }]
    payload = _payload(12, 6, warnings)
    hard = compute_hard_metrics(payload, ip_must_have=[])
    clean = compute_hard_metrics(_payload(12, 6, []), ip_must_have=[])
    assert hard["prune_count"] == 5
    assert hard["prune_penalty"] == 20.0   # 5*4 封顶 20
    assert hard["overall_score"] == round(max(0.0, clean["overall_score"] - 20.0), 1)
