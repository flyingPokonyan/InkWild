"""Guardrail: smoke actions must be source-agnostic. Pre-2026-05-24 the
runner hardcoded `第七版结局`, which leaked the short-drama source into
every world we tested and distorted both Director context and Tier1
scoring on non-short-drama sources.
"""
from __future__ import annotations

import re
from pathlib import Path


def test_smoke_actions_have_no_source_specific_keywords():
    runner = (
        Path(__file__).resolve().parents[2]
        / "experiments/2026-05-vps-eval/runner/session_runner.py"
    )
    assert runner.exists(), f"smoke runner not found at {runner}"
    text = runner.read_text(encoding="utf-8")
    match = re.search(r"SMOKE_ACTIONS\s*=\s*\[(.*?)\]", text, flags=re.S)
    assert match, "SMOKE_ACTIONS list not found in runner"
    actions_block = match.group(1)
    forbidden = ["第七版结局", "短剧", "编剧室", "竖屏", "复仇短剧"]
    leaked = [word for word in forbidden if word in actions_block]
    assert not leaked, (
        f"Source-specific words leaked into SMOKE_ACTIONS: {leaked}. "
        "Use neutral phrasing referencing 'core mystery' / 'current anomaly' "
        "so the same actions work across all sources."
    )
