"""Per-slot reasoning (thinking) on/off policy.

Thinking-capable models (deepseek-v4-pro) leak hidden CoT that never reaches
the result but burns output tokens + latency. Realtime + generation slots
already disable it. The compression slot did not — and NPC reflection borrows
the compression router (game_service → orchestrator.compression_llm_router), so
both compression and reflection leaked CoT (~21 reflection calls/session in the
2026-06 soaks). Both are structured-summary tasks where CoT is pure waste.
"""
from __future__ import annotations

from services.model_management import _reasoning_for_slot


def test_realtime_slots_disable_reasoning():
    assert _reasoning_for_slot("game_main") is False
    assert _reasoning_for_slot("npc_agent") is False


def test_generation_slots_disable_reasoning():
    assert _reasoning_for_slot("admin_generation") is False


def test_compression_slot_disables_reasoning():
    # reflection rides this router — fixing the slot fixes both leaks.
    assert _reasoning_for_slot("conversation_compression") is False


def test_player_facing_narrative_slot_keeps_reasoning():
    # ending_summary produces player-facing narrative; leave CoT available.
    assert _reasoning_for_slot("ending_summary") is None
