"""B1: the compaction debounce counter must be stamped on the turn's owned
GameState (persisted by the main loop, BEFORE the early-stream state snapshot),
not written from the detached fire-and-forget task into a plain-JSON column
(silently dropped + clobbered). Regression: compaction used to re-fire every
round past the threshold because last_compressed_round never advanced.

Ordering coverage (stamp must precede the committed snapshot) lives in
test_orchestrator_v2_loading.py::test_compression_counter_stamped_before_state_snapshot.
"""

import types

from engine.orchestrator import Orchestrator


def _orch():
    return Orchestrator(llm_router=object())


def test_claim_compression_stamps_and_returns_true_when_due():
    orch = _orch()
    state = types.SimpleNamespace(round_number=22, last_compressed_round=0)

    assert orch._claim_compression(state) is True
    assert state.last_compressed_round == 22


def test_claim_compression_debounces_within_gap():
    orch = _orch()
    state = types.SimpleNamespace(round_number=22, last_compressed_round=0)
    assert orch._claim_compression(state) is True  # stamps 22

    # Next rounds within MIN_GAP(10) of the stamp must not re-claim.
    state.round_number = 27
    assert orch._claim_compression(state) is False
    assert state.last_compressed_round == 22  # unchanged

    # MIN_GAP elapsed → claims again.
    state.round_number = 32
    assert orch._claim_compression(state) is True
    assert state.last_compressed_round == 32


def test_claim_compression_returns_false_before_threshold():
    orch = _orch()
    state = types.SimpleNamespace(round_number=15, last_compressed_round=0)
    assert orch._claim_compression(state) is False
    assert state.last_compressed_round == 0
