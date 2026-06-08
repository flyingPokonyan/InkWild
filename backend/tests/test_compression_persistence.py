"""B1: the compression debounce counter must be advanced on the turn's owned
GameState (persisted by the main loop under the optimistic lock), not written
from the detached fire-and-forget task into a plain-JSON column (silently
dropped + clobbered). Regression: compression used to re-fire every round past
the threshold because last_compressed_round never advanced."""

import asyncio
import types

import pytest

from engine.orchestrator import Orchestrator


def _orch(monkeypatch):
    orch = Orchestrator(llm_router=object())
    calls = []

    async def _fake_retry(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(orch, "_run_compression_with_retry", _fake_retry)
    return orch, calls


@pytest.mark.asyncio
async def test_maybe_compress_stamps_owned_state_counter(monkeypatch):
    orch, calls = _orch(monkeypatch)
    state = types.SimpleNamespace(round_number=22, last_compressed_round=0)

    orch._maybe_compress("sess", state)
    await asyncio.sleep(0)  # let the scheduled task run

    assert state.last_compressed_round == 22
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_maybe_compress_debounces_within_gap(monkeypatch):
    orch, calls = _orch(monkeypatch)
    state = types.SimpleNamespace(round_number=22, last_compressed_round=0)

    orch._maybe_compress("sess", state)
    await asyncio.sleep(0)

    state.round_number = 24  # within MIN_GAP(5) of the stamp at 22
    orch._maybe_compress("sess", state)
    await asyncio.sleep(0)

    assert state.last_compressed_round == 22  # not advanced
    assert len(calls) == 1  # not rescheduled
